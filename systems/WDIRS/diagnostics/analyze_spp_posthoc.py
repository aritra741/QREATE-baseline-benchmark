#!/usr/bin/env python3
"""Decompose a sealed SPP run using evaluation-only ground truth.

This module is deliberately outside the synthesis path. It reads an immutable
serving bundle only after its seal has been verified and never writes any result
back into a synthesis cache, evidence store, database, or workload contract.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple

WDIRS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WDIRS_ROOT.parent.parent
for import_root in (WDIRS_ROOT, PROJECT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from diagnostics.evaluate_native_spp_bundle import (  # noqa: E402
    _reference_queries,
    _score_query,
    _sha256,
)
from diagnostics.run_config_grid import (  # noqa: E402
    load_attributes,
    load_ground_truth,
)
from spp.aggregation_metrics import MetricConfig  # noqa: E402
from spp.config_grid import _build_in_memory_db, _execute_sql  # noqa: E402
from spp.population_config import PopulationConfig  # noqa: E402
from spp.query_plan_compiler import compile_query_plan  # noqa: E402
from spp.query_quality import QueryExecutionError, execute_readonly  # noqa: E402
from spp.serving import OfflineQueryServer  # noqa: E402
from spp.spec import (  # noqa: E402
    AggregateSpec,
    AttributeRef,
    HavingSpec,
    JoinSpec,
    PredicateSpec,
    PreprocessingPolicy,
    QueryPlan,
    QueryRequirement,
    RelationSpec,
    SchemaDesign,
    SynthesisConfig,
)
from spp.workload_intent import (  # noqa: E402
    _sql_requirement,
    workload_intent_from_payload,
)


def _predicate_shape(predicate: Optional[PredicateSpec]) -> object:
    if predicate is None:
        return None
    if predicate.kind in {"and", "or"}:
        return (
            predicate.kind,
            tuple(_predicate_shape(child) for child in predicate.children),
        )
    return (
        "predicate",
        predicate.operator,
        json.dumps(predicate.value, sort_keys=True, default=str),
    )


def _plan_shape(plan: Optional[QueryPlan]) -> Mapping[str, object]:
    if plan is None:
        return {
            "projections": None,
            "group_by": None,
            "aggregates": None,
            "predicate": None,
            "joins": None,
            "having": None,
        }
    return {
        "projections": len(plan.projections),
        "group_by": len(plan.group_by),
        "aggregates": tuple(
            (aggregate.function, aggregate.distinct)
            for aggregate in plan.aggregates
        ),
        "predicate": _predicate_shape(plan.predicate),
        "joins": tuple(join.join_type for join in plan.joins),
        "having": tuple(
            (
                item.aggregate.function,
                item.aggregate.distinct,
                item.operator,
                json.dumps(item.value, sort_keys=True, default=str),
            )
            for item in plan.having
        ),
    }


def _plan_shape_score(
    generated: Optional[QueryPlan],
    reference: Optional[QueryPlan],
) -> Tuple[float, Mapping[str, bool]]:
    generated_shape = _plan_shape(generated)
    reference_shape = _plan_shape(reference)
    agreement = {
        key: generated_shape[key] == reference_shape[key]
        for key in generated_shape
    }
    return (
        sum(agreement.values()) / len(agreement) if agreement else 0.0,
        agreement,
    )


def _role_align_plan(
    generated: QueryPlan,
    reference: QueryPlan,
) -> Tuple[QueryPlan, Tuple[str, ...]]:
    """Align symbols by query role while preserving generated operations."""

    bindings: Dict[AttributeRef, AttributeRef] = {}
    conflicts: set[str] = set()

    def bind(
        generated_ref: Optional[AttributeRef],
        reference_ref: Optional[AttributeRef],
    ) -> None:
        if generated_ref is None or reference_ref is None:
            return
        previous = bindings.get(generated_ref)
        if previous is not None and previous != reference_ref:
            conflicts.add(
                f"{generated_ref.entity}.{generated_ref.attribute}"
            )
            return
        bindings[generated_ref] = reference_ref

    for generated_ref, reference_ref in zip(
        generated.projections, reference.projections
    ):
        bind(generated_ref, reference_ref)
    for generated_ref, reference_ref in zip(
        generated.group_by, reference.group_by
    ):
        bind(generated_ref, reference_ref)
    for generated_item, reference_item in zip(
        generated.aggregates, reference.aggregates
    ):
        bind(generated_item.attribute, reference_item.attribute)
    for generated_item, reference_item in zip(
        generated.joins, reference.joins
    ):
        bind(generated_item.left, reference_item.left)
        bind(generated_item.right, reference_item.right)
    for generated_item, reference_item in zip(
        generated.having, reference.having
    ):
        bind(
            generated_item.aggregate.attribute,
            reference_item.aggregate.attribute,
        )

    def bind_predicates(
        generated_item: Optional[PredicateSpec],
        reference_item: Optional[PredicateSpec],
    ) -> None:
        if generated_item is None or reference_item is None:
            return
        if (
            generated_item.kind == "predicate"
            and reference_item.kind == "predicate"
        ):
            bind(generated_item.attribute, reference_item.attribute)
            return
        for generated_child, reference_child in zip(
            generated_item.children, reference_item.children
        ):
            bind_predicates(generated_child, reference_child)

    bind_predicates(generated.predicate, reference.predicate)

    def aligned(reference: Optional[AttributeRef]) -> Optional[AttributeRef]:
        if reference is None:
            return None
        return bindings.get(reference, reference)

    def predicate(item: Optional[PredicateSpec]) -> Optional[PredicateSpec]:
        if item is None:
            return None
        if item.kind == "predicate":
            return replace(item, attribute=aligned(item.attribute))
        return replace(
            item,
            children=tuple(predicate(child) for child in item.children),
        )

    return (
        QueryPlan(
            projections=tuple(aligned(item) for item in generated.projections),
            group_by=tuple(aligned(item) for item in generated.group_by),
            aggregates=tuple(
                replace(item, attribute=aligned(item.attribute))
                for item in generated.aggregates
            ),
            predicate=predicate(generated.predicate),
            joins=tuple(
                JoinSpec(
                    aligned(item.left),
                    aligned(item.right),
                    item.join_type,
                )
                for item in generated.joins
            ),
            having=tuple(
                HavingSpec(
                    aggregate=replace(
                        item.aggregate,
                        attribute=aligned(item.aggregate.attribute),
                    ),
                    operator=item.operator,
                    value=item.value,
                )
                for item in generated.having
            ),
        ),
        tuple(sorted(conflicts)),
    )


def _schema_from_payload(payload: Mapping[str, object]) -> SchemaDesign:
    relations = tuple(
        RelationSpec(
            name=str(item["name"]),
            attributes=tuple(str(value) for value in item["attributes"]),
            primary_key=(
                str(item["primary_key"])
                if item.get("primary_key") is not None
                else None
            ),
            foreign_keys=tuple(
                tuple(str(value) for value in row)
                for row in item.get("foreign_keys", ())
            ),
            semantic_types=tuple(
                tuple(str(value) for value in row)
                for row in item.get("semantic_types", ())
            ),
        )
        for item in payload.get("relations", ())
    )
    return SchemaDesign(
        pattern=str(payload["pattern"]),
        relations=relations,
        covered_query_ids=tuple(
            str(value) for value in payload.get("covered_query_ids", ())
        ),
        description=str(payload.get("description", "")),
    )


def _configs_from_manifest(
    synthesis: Mapping[str, object],
) -> Mapping[str, SynthesisConfig]:
    candidate_space = synthesis["candidate_space"]
    schemas = {
        schema_id: _schema_from_payload(payload)
        for schema_id, payload in candidate_space["schemas"].items()
    }
    populations = {
        population_id: PopulationConfig(**payload)
        for population_id, payload in candidate_space[
            "population_configs"
        ].items()
    }
    preprocessing = {
        policy_id: PreprocessingPolicy(**payload)
        for policy_id, payload in candidate_space[
            "preprocessing_policies"
        ].items()
    }
    return {
        str(item["config_id"]): SynthesisConfig(
            schema=schemas[str(item["schema_id"])],
            population=populations[str(item["population_config_id"])],
            preprocessing=preprocessing[
                str(item["preprocessing_policy_id"])
            ],
        )
        for item in candidate_space["configs"]
    }


def _ground_truth_config(
    ground_truth: Mapping[str, Sequence[Mapping[str, object]]],
    query_ids: Sequence[str],
) -> SynthesisConfig:
    relations = []
    for name, rows in sorted(ground_truth.items()):
        attributes = tuple(
            dict.fromkeys(
                str(column)
                for row in rows
                for column in row
            )
        )
        relations.append(
            RelationSpec(
                name=str(name),
                attributes=attributes,
                semantic_types=tuple(
                    (column, "text") for column in attributes
                ),
            )
        )
    return SynthesisConfig(
        schema=SchemaDesign(
            pattern="snowflake",
            relations=tuple(relations),
            covered_query_ids=tuple(query_ids),
            description="Evaluation-only canonical schema.",
        ),
        population=PopulationConfig(),
        preprocessing=PreprocessingPolicy("whole_document"),
    )


def _metric_value(row: Mapping[str, object], tau: float) -> float:
    values = row.get("query_score", {})
    if not isinstance(values, Mapping):
        return 0.0
    return float(values.get(str(float(tau)), 0.0))


def _mean(values: Sequence[float]) -> float:
    return statistics.mean(values) if values else 0.0


def _routing_summary(
    matrix: Mapping[str, Mapping[str, Mapping[str, object]]],
    selected_routing: Mapping[str, str],
    query_ids: Sequence[str],
    *,
    tau: float,
) -> Mapping[str, object]:
    selected_scores: Dict[str, float] = {}
    oracle_scores: Dict[str, float] = {}
    oracle_routing: Dict[str, str] = {}
    for query_id in query_ids:
        selected_config = str(selected_routing.get(query_id, ""))
        selected_scores[query_id] = _metric_value(
            matrix.get(selected_config, {}).get(query_id, {}),
            tau,
        )
        ranked = sorted(
            (
                _metric_value(rows.get(query_id, {}), tau),
                config_id,
            )
            for config_id, rows in matrix.items()
        )
        oracle_score, oracle_config = (
            ranked[-1] if ranked else (0.0, "")
        )
        oracle_scores[query_id] = oracle_score
        oracle_routing[query_id] = oracle_config

    candidate_means = {
        config_id: _mean(
            [_metric_value(rows.get(query_id, {}), tau) for query_id in query_ids]
        )
        for config_id, rows in matrix.items()
    }
    best_single = max(
        candidate_means,
        key=lambda config_id: (candidate_means[config_id], config_id),
        default="",
    )
    selected_mean = _mean(list(selected_scores.values()))
    oracle_mean = _mean(list(oracle_scores.values()))
    return {
        "selected_mean_query_score": selected_mean,
        "materialized_oracle_mean_query_score": oracle_mean,
        "routing_regret": oracle_mean - selected_mean,
        "best_single_config_id": best_single,
        "best_single_mean_query_score": candidate_means.get(best_single, 0.0),
        "candidate_mean_query_scores": candidate_means,
        "oracle_query_to_config": oracle_routing,
        "selected_per_query": selected_scores,
        "oracle_per_query": oracle_scores,
    }


def analyze(
    *,
    bundle: Path,
    synthesis_manifest: Path,
    reference_workload: Path,
    dataset: str,
    tau: float,
    max_rows: int,
    materialized_dir: Optional[Path] = None,
) -> Mapping[str, object]:
    bundle = Path(bundle).expanduser().resolve()
    synthesis_manifest = Path(synthesis_manifest).expanduser().resolve()
    reference_workload = Path(reference_workload).expanduser().resolve()
    # This verifies the seal plus all database and frozen SQL hashes before any
    # evaluation-only reference is loaded.
    OfflineQueryServer(bundle)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    expected_synthesis_sha = str(
        manifest.get("synthesis_manifest_sha256", "")
    )
    if (
        not expected_synthesis_sha
        or _sha256(synthesis_manifest) != expected_synthesis_sha
    ):
        raise ValueError(
            "synthesis manifest does not match the sealed serving bundle"
        )
    synthesis = json.loads(synthesis_manifest.read_text())
    references = _reference_queries(reference_workload)
    query_ids = tuple(
        str(item["query_id"]) for item in manifest["queries"]
    )
    if set(query_ids) != set(references):
        raise ValueError("reference and sealed workload query IDs differ")

    intent_payload = {"version": 2, **synthesis["workload_intent"]}
    intent = workload_intent_from_payload(intent_payload)
    requirements = {
        requirement.query_id: requirement
        for requirement in intent.requirements
    }
    configs = _configs_from_manifest(synthesis)
    frozen_queries = {
        str(item["query_id"]): item for item in manifest["queries"]
    }
    database_artifacts: Dict[str, Mapping[str, object]] = {
        str(item["config_id"]): {
            "path": bundle / str(item["filename"]),
            "origin": "sealed_serving_bundle",
            "sha256": str(item["sha256"]),
        }
        for item in manifest["databases"]
    }
    candidate_dir = (
        Path(materialized_dir).expanduser().resolve()
        if materialized_dir is not None
        else synthesis_manifest.parent / "materialized_work"
    )
    if candidate_dir.is_dir():
        for config_id in configs:
            filename = (
                hashlib.sha256(config_id.encode()).hexdigest()[:16]
                + ".sqlite"
            )
            path = candidate_dir / filename
            if config_id not in database_artifacts and path.is_file():
                database_artifacts[config_id] = {
                    "path": path,
                    "origin": "run_materialized_work",
                    "sha256": _sha256(path),
                }
    evaluation_config = MetricConfig(tau_sweep=(float(tau),))
    ground_truth = load_ground_truth(dataset)
    attributes = load_attributes(dataset)
    ground_truth_connection = _build_in_memory_db(ground_truth)
    gold_rows = {
        query_id: _execute_sql(
            ground_truth_connection, references[query_id]
        )
        for query_id in query_ids
    }

    matrix: Dict[str, Dict[str, Mapping[str, object]]] = {}
    for config_id, artifact in database_artifacts.items():
        config = configs.get(config_id)
        database_path = Path(str(artifact["path"]))
        matrix[config_id] = {}
        for query_id in query_ids:
            requirement = requirements.get(query_id)
            sql = None
            compile_error = None
            if frozen_queries[query_id]["config_id"] == config_id:
                # Preserve the exact deployed route. Alternative databases use
                # the same frozen typed plan recompiled against their schema.
                sql = str(frozen_queries[query_id]["sql"])
            elif config is not None and requirement is not None:
                try:
                    sql = compile_query_plan(requirement.plan, config)
                except (ValueError, KeyError) as exc:
                    compile_error = str(exc)
            if sql is None:
                matrix[config_id][query_id] = {
                    "error": compile_error
                    or "typed plan cannot bind to candidate schema",
                    "query_score": {str(float(tau)): 0.0},
                    "official_accuracy": 0.0,
                }
                continue
            try:
                execution = execute_readonly(
                    database_path, sql, max_rows=max_rows
                )
                scored = _score_query(
                    references[query_id],
                    gold_rows[query_id],
                    list(execution.rows),
                    attributes,
                    config=evaluation_config,
                )
                scored["sql"] = sql
                scored["row_count"] = execution.row_count
                matrix[config_id][query_id] = scored
            except (QueryExecutionError, ValueError) as exc:
                matrix[config_id][query_id] = {
                    "error": str(exc),
                    "sql": sql,
                    "query_score": {str(float(tau)): 0.0},
                    "official_accuracy": 0.0,
                }

    gt_config = _ground_truth_config(ground_truth, query_ids)
    plan_ceiling: Dict[str, Mapping[str, object]] = {}
    for query_id in query_ids:
        generated = requirements[query_id].plan
        reference_requirement = _sql_requirement(
            query_id, references[query_id]
        )
        reference_plan = reference_requirement.plan
        shape_score, shape_agreement = _plan_shape_score(
            generated, reference_plan
        )
        row: Dict[str, object] = {
            "shape_score": shape_score,
            "shape_agreement": shape_agreement,
        }
        if generated is None or reference_plan is None:
            row.update(
                {
                    "error": "generated or reference plan is unavailable",
                    "query_score": None,
                }
            )
            plan_ceiling[query_id] = row
            continue
        aligned, conflicts = _role_align_plan(generated, reference_plan)
        try:
            sql = compile_query_plan(aligned, gt_config)
        except (ValueError, KeyError) as exc:
            sql = None
            row["compile_error"] = str(exc)
        row["role_alignment_conflicts"] = list(conflicts)
        row["sql"] = sql
        if sql is None or conflicts:
            row.update(
                {
                    "error": "role-aligned plan cannot bind canonical schema",
                    "query_score": None,
                }
            )
            plan_ceiling[query_id] = row
            continue
        try:
            predicted = _execute_sql(ground_truth_connection, sql)
            scored = _score_query(
                references[query_id],
                gold_rows[query_id],
                predicted,
                attributes,
                config=evaluation_config,
            )
            row["query_score"] = _metric_value(scored, tau)
            row["official_accuracy"] = float(
                scored["official_accuracy"]
            )
            row["row_count"] = len(predicted)
        except Exception as exc:
            row["error"] = str(exc)
            row["query_score"] = None
        plan_ceiling[query_id] = row

    ground_truth_connection.close()
    routing = _routing_summary(
        matrix,
        manifest["portfolio"]["query_to_config"],
        query_ids,
        tau=tau,
    )
    shape_scores = [
        float(plan_ceiling[query_id]["shape_score"])
        for query_id in query_ids
    ]
    bindable_query_ids = [
        query_id
        for query_id in query_ids
        if not bool(plan_ceiling[query_id].get("error"))
        and plan_ceiling[query_id].get("query_score") is not None
    ]
    plan_scores = [
        float(plan_ceiling[query_id]["query_score"])
        for query_id in bindable_query_ids
    ]
    plan_bindable = len(bindable_query_ids)
    plan_mean = _mean(plan_scores)
    per_query_decomposition = {}
    for query_id in query_ids:
        raw_plan_score = plan_ceiling[query_id].get("query_score")
        plan_score = (
            float(raw_plan_score)
            if raw_plan_score is not None
            else None
        )
        oracle_score = float(routing["oracle_per_query"][query_id])
        routed_score = float(routing["selected_per_query"][query_id])
        per_query_decomposition[query_id] = {
            "plan_role_aligned_score": plan_score,
            "materialized_oracle_score": oracle_score,
            "selected_route_score": routed_score,
            "plan_semantic_loss": (
                max(0.0, 1.0 - plan_score)
                if plan_score is not None
                else None
            ),
            "materialization_loss": (
                max(0.0, plan_score - oracle_score)
                if plan_score is not None
                else None
            ),
            "routing_loss": max(0.0, oracle_score - routed_score),
            "selected_config_id": str(
                manifest["portfolio"]["query_to_config"].get(query_id, "")
            ),
            "oracle_config_id": str(
                routing["oracle_query_to_config"].get(query_id, "")
            ),
        }
    bindable_materialization_losses = [
        max(
            0.0,
            float(plan_ceiling[query_id]["query_score"])
            - float(routing["oracle_per_query"][query_id]),
        )
        for query_id in bindable_query_ids
    ]
    bindable_routing_losses = [
        max(
            0.0,
            float(routing["oracle_per_query"][query_id])
            - float(routing["selected_per_query"][query_id]),
        )
        for query_id in bindable_query_ids
    ]
    losses: Mapping[str, Optional[float]]
    if bindable_query_ids:
        losses = {
            "plan_semantic_loss": max(0.0, 1.0 - plan_mean),
            "materialization_loss": _mean(
                bindable_materialization_losses
            ),
            "routing_loss": _mean(bindable_routing_losses),
        }
        dominant = max(
            losses,
            key=lambda key: (float(losses[key] or 0.0), key),
        )
    else:
        losses = {
            "plan_semantic_loss": None,
            "materialization_loss": None,
            "routing_loss": None,
        }
        dominant = "insufficient_plan_coverage"
    return {
        "method": "sealed_spp_posthoc_decomposition",
        "evaluation_only": True,
        "feeds_synthesis": False,
        "dataset": dataset,
        "tau": float(tau),
        "sealed_manifest_sha256": _sha256(manifest_path),
        "reference_workload_sha256": _sha256(reference_workload),
        "query_count": len(query_ids),
        "materialized_config_count": len(database_artifacts),
        "candidate_artifacts": {
            config_id: {
                "path": str(artifact["path"]),
                "origin": str(artifact["origin"]),
                "sha256": str(artifact["sha256"]),
            }
            for config_id, artifact in database_artifacts.items()
        },
        "plan_ceiling": {
            "role_aligned_mean_query_score": plan_mean,
            "mean_shape_score": _mean(shape_scores),
            "bindable_query_count": plan_bindable,
            "coverage_fraction": (
                plan_bindable / len(query_ids) if query_ids else 0.0
            ),
            "unbound_query_ids": sorted(
                set(query_ids) - set(bindable_query_ids)
            ),
            "per_query": plan_ceiling,
        },
        "candidate_matrix": matrix,
        "routing": routing,
        "decomposition": {
            **losses,
            "basis": (
                "Loss components are means over role-aligned, bindable plan "
                "queries only. Unbindable checks are unknown, not zero."
            ),
            "overall_routing_regret": routing["routing_regret"],
            "dominant_observed_bottleneck": dominant,
            "per_query": per_query_decomposition,
            "scope_note": (
                "The candidate ceiling ranges over sealed serving databases "
                "plus deterministic database artifacts retained in the run's "
                "materialized_work directory. Unmaterialized candidate-space "
                "points cannot be scored because no database artifact exists."
            ),
        },
        "verifier_statuses": dict(
            Counter(
                item.get("status", "unknown")
                for item in synthesis.get("backend", {})
                .get("cell_verification", {})
                .get("summary", {})
                .get("decisions", ())
                if isinstance(item, Mapping)
            )
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Post-hoc plan, materialization, and routing decomposition for a "
            "sealed native-SPP run."
        )
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--synthesis-manifest", type=Path, required=True)
    parser.add_argument("--reference-workload", type=Path, required=True)
    parser.add_argument("--dataset", default="Player")
    parser.add_argument("--tau", type=float, default=0.2)
    parser.add_argument("--max-rows", type=int, default=100_000)
    parser.add_argument(
        "--materialized-dir",
        type=Path,
        default=None,
        help=(
            "Optional preliminary database directory. Defaults to "
            "<synthesis-manifest parent>/materialized_work."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze(
        bundle=args.bundle,
        synthesis_manifest=args.synthesis_manifest,
        reference_workload=args.reference_workload,
        dataset=args.dataset,
        tau=args.tau,
        max_rows=args.max_rows,
        materialized_dir=args.materialized_dir,
    )
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, default=str))
    summary = {
        "plan_role_aligned_mean_query_score": report["plan_ceiling"][
            "role_aligned_mean_query_score"
        ],
        "plan_mean_shape_score": report["plan_ceiling"][
            "mean_shape_score"
        ],
        "plan_bindable_queries": report["plan_ceiling"][
            "bindable_query_count"
        ],
        "selected_mean_query_score": report["routing"][
            "selected_mean_query_score"
        ],
        "materialized_oracle_mean_query_score": report["routing"][
            "materialized_oracle_mean_query_score"
        ],
        "routing_regret": report["routing"]["routing_regret"],
        "best_single_config_id": report["routing"][
            "best_single_config_id"
        ],
        "best_single_mean_query_score": report["routing"][
            "best_single_mean_query_score"
        ],
        "decomposition": report["decomposition"],
        "output": str(output),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

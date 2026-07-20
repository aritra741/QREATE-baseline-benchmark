"""Leakage-free paper experiment harness for frozen serving bundles."""

from __future__ import annotations

import json
import os
import random
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

from spp.oracle_evaluation import OracleReferences, file_sha256
from spp.serving import OfflineQueryServer


@dataclass(frozen=True)
class EvaluationResult:
    method: str
    budget: int
    consumed_tokens: int
    unused_tokens: int
    mean_error: float
    per_query_error: Mapping[str, float]
    selected_database_count: int
    storage_bytes: int
    synthesis_seconds: float
    manifest_sha256: str
    ablation: Optional[str] = None
    scale_label: Optional[str] = None


def docetl_relative_budgets(
    docetl_tokens: int,
    fractions: Sequence[float] = (0.05, 0.10, 0.20, 0.50, 1.0),
) -> List[int]:
    if docetl_tokens <= 0:
        raise ValueError("DocETL token reference must be positive")
    if any(fraction <= 0 for fraction in fractions):
        raise ValueError("budget fractions must be positive")
    return sorted({int(round(docetl_tokens * fraction)) for fraction in fractions})


def evaluate_frozen_bundle(
    bundle_dir: Path,
    ground_truth_answers: Mapping[str, Sequence[dict]],
    error_metric: Callable[[Sequence[dict], Sequence[dict]], float],
    *,
    method: str,
    budget: int,
    synthesis_seconds: float,
    ablation: Optional[str] = None,
    scale_label: Optional[str] = None,
) -> EvaluationResult:
    """Evaluate only after decisions, routing and SQL have been sealed."""
    bundle_dir = Path(bundle_dir).expanduser().resolve()
    manifest_path = bundle_dir / "manifest.json"
    if not (bundle_dir / "SEALED").exists():
        raise ValueError("refusing to evaluate an unsealed deployment")
    manifest = json.loads(manifest_path.read_text())
    server = OfflineQueryServer(bundle_dir)
    query_ids = [row["query_id"] for row in manifest["queries"]]
    if set(query_ids) != set(ground_truth_answers):
        raise ValueError("ground-truth query IDs do not match frozen workload")
    errors = {
        query_id: float(
            error_metric(server.execute(query_id), ground_truth_answers[query_id])
        )
        for query_id in query_ids
    }
    consumed = int(manifest["portfolio"]["construction_tokens"])
    return EvaluationResult(
        method=method,
        budget=int(budget),
        consumed_tokens=consumed,
        unused_tokens=max(int(budget) - consumed, 0),
        mean_error=statistics.mean(errors.values()) if errors else float("nan"),
        per_query_error=errors,
        selected_database_count=len(manifest["databases"]),
        storage_bytes=sum(
            int(artifact["size_bytes"]) for artifact in manifest["databases"]
        ),
        synthesis_seconds=float(synthesis_seconds),
        manifest_sha256=file_sha256(manifest_path),
        ablation=ablation,
        scale_label=scale_label,
    )


def regret_metrics(
    result: EvaluationResult, oracle: OracleReferences
) -> Dict[str, float]:
    return {
        "single_config_regret": result.mean_error - oracle.best_single_error,
        "budgeted_portfolio_regret": (
            result.mean_error - oracle.budgeted_mean_error
        ),
        "per_query_oracle_gap": (
            result.mean_error - oracle.per_query_oracle_error
        ),
    }


def paired_noninferiority_report(
    proposed: EvaluationResult,
    baseline: EvaluationResult,
    *,
    bootstrap_rounds: int = 2_000,
    seed: int = 42,
) -> dict:
    """Paired error comparison with regression fraction and bootstrap CI."""
    query_ids = sorted(
        set(proposed.per_query_error) & set(baseline.per_query_error)
    )
    if not query_ids:
        raise ValueError("methods have no common query IDs")
    if bootstrap_rounds <= 0:
        raise ValueError("bootstrap_rounds must be positive")
    # Positive improvement means the proposed system has lower error.
    improvements = [
        baseline.per_query_error[qid] - proposed.per_query_error[qid]
        for qid in query_ids
    ]
    rng = random.Random(seed)
    bootstrap_means = []
    for _ in range(bootstrap_rounds):
        sample = [rng.choice(improvements) for _ in improvements]
        bootstrap_means.append(statistics.mean(sample))
    bootstrap_means.sort()
    lower_index = int(0.025 * (len(bootstrap_means) - 1))
    upper_index = int(0.975 * (len(bootstrap_means) - 1))
    regressions = {
        query_id: (
            proposed.per_query_error[query_id]
            - baseline.per_query_error[query_id]
        )
        for query_id in query_ids
        if proposed.per_query_error[query_id]
        > baseline.per_query_error[query_id]
    }
    return {
        "mean_accuracy_improvement": statistics.mean(improvements),
        "improvement_95ci": [
            bootstrap_means[lower_index],
            bootstrap_means[upper_index],
        ],
        "regression_fraction": len(regressions) / len(query_ids),
        "worst_query_regression": max(regressions.values(), default=0.0),
        "regressed_query_ids": sorted(regressions),
    }


def selector_top_k_recall(
    ranked_config_ids: Sequence[str],
    oracle_winner_ids: Iterable[str],
    *,
    k: int,
) -> float:
    winners = set(oracle_winner_ids)
    if not winners:
        return 1.0
    return len(set(ranked_config_ids[:k]) & winners) / len(winners)


def run_multi_budget_experiment(
    *,
    budgets: Sequence[int],
    synthesize: Callable[[int, Path], Path],
    ground_truth_answers: Mapping[str, Sequence[dict]],
    error_metric: Callable[[Sequence[dict], Sequence[dict]], float],
    output_root: Path,
    method: str = "spp",
    ablation: Optional[str] = None,
    scale_label: Optional[str] = None,
) -> List[EvaluationResult]:
    """Run isolated synthesis then evaluation at each end-to-end budget."""
    output_root = Path(output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    results: List[EvaluationResult] = []
    for budget in sorted(set(int(value) for value in budgets)):
        run_dir = output_root / f"budget_{budget}"
        if run_dir.exists():
            raise FileExistsError(f"experiment output already exists: {run_dir}")
        started = time.monotonic()
        manifest_path = Path(synthesize(budget, run_dir)).resolve()
        synthesis_seconds = time.monotonic() - started
        bundle_dir = manifest_path.parent
        # The synthesis callback receives no GT object. GT enters only here,
        # after a sealed artifact exists.
        results.append(
            evaluate_frozen_bundle(
                bundle_dir,
                ground_truth_answers,
                error_metric,
                method=method,
                budget=budget,
                synthesis_seconds=synthesis_seconds,
                ablation=ablation,
                scale_label=scale_label,
            )
        )
    save_experiment_results(results, output_root / "evaluation_results.json")
    return results


def run_process_isolated_multi_budget_experiment(
    *,
    budgets: Sequence[int],
    command_factory: Callable[[int, Path], Sequence[str]],
    manifest_locator: Callable[[Path], Path],
    ground_truth_answers: Mapping[str, Sequence[dict]],
    error_metric: Callable[[Sequence[dict], Sequence[dict]], float],
    output_root: Path,
    method: str = "spp",
) -> List[EvaluationResult]:
    """Paper protocol: synthesis runs in a child process that cannot receive GT."""
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    results: List[EvaluationResult] = []
    for budget in sorted(set(int(value) for value in budgets)):
        run_dir = root / f"budget_{budget}"
        if run_dir.exists():
            raise FileExistsError(run_dir)
        command = list(command_factory(budget, run_dir))
        environment = {
            key: value
            for key, value in os.environ.items()
            if "GROUND_TRUTH" not in key.upper() and not key.upper().startswith("GT_")
        }
        environment["SPP_TRACK"] = "deployable"
        started = time.monotonic()
        subprocess.run(command, check=True, env=environment)
        elapsed = time.monotonic() - started
        manifest = manifest_locator(run_dir).resolve()
        if not manifest.exists() or not (manifest.parent / "SEALED").exists():
            raise RuntimeError("synthesis process did not emit a sealed artifact")
        results.append(
            evaluate_frozen_bundle(
                manifest.parent,
                ground_truth_answers,
                error_metric,
                method=method,
                budget=budget,
                synthesis_seconds=elapsed,
            )
        )
    save_experiment_results(results, root / "evaluation_results.json")
    return results


def run_experiment_matrix(
    *,
    budgets: Sequence[int],
    synthesizers: Mapping[
        str, Callable[[int, Path], Path]
    ],
    ground_truth_answers: Mapping[str, Sequence[dict]],
    error_metric: Callable[[Sequence[dict], Sequence[dict]], float],
    output_root: Path,
    ablation_synthesizers: Optional[
        Mapping[str, Callable[[int, Path], Path]]
    ] = None,
    scale_synthesizers: Optional[
        Mapping[str, Callable[[int, Path], Path]]
    ] = None,
) -> List[EvaluationResult]:
    """Run proposed method, baselines, ablations and scalability variants."""
    root = Path(output_root).expanduser().resolve()
    all_results: List[EvaluationResult] = []
    for method, synthesizer in synthesizers.items():
        all_results.extend(
            run_multi_budget_experiment(
                budgets=budgets,
                synthesize=synthesizer,
                ground_truth_answers=ground_truth_answers,
                error_metric=error_metric,
                output_root=root / "methods" / method,
                method=method,
            )
        )
    for ablation, synthesizer in (ablation_synthesizers or {}).items():
        all_results.extend(
            run_multi_budget_experiment(
                budgets=budgets,
                synthesize=synthesizer,
                ground_truth_answers=ground_truth_answers,
                error_metric=error_metric,
                output_root=root / "ablations" / ablation,
                method="spp",
                ablation=ablation,
            )
        )
    for scale_label, synthesizer in (scale_synthesizers or {}).items():
        all_results.extend(
            run_multi_budget_experiment(
                budgets=budgets,
                synthesize=synthesizer,
                ground_truth_answers=ground_truth_answers,
                error_metric=error_metric,
                output_root=root / "scalability" / scale_label,
                method="spp",
                scale_label=scale_label,
            )
        )
    save_experiment_results(all_results, root / "experiment_matrix.json")
    return all_results


def summarize_accuracy_cost_frontier(
    results: Iterable[EvaluationResult],
) -> List[EvaluationResult]:
    """Return nondominated points (lower error and lower tokens are better)."""
    ordered = sorted(
        results, key=lambda result: (result.consumed_tokens, result.mean_error)
    )
    frontier: List[EvaluationResult] = []
    best_error = float("inf")
    for result in ordered:
        if result.mean_error < best_error:
            frontier.append(result)
            best_error = result.mean_error
    return frontier


def save_experiment_results(
    results: Sequence[EvaluationResult], path: Path
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps([asdict(result) for result in results], indent=2))
    tmp.replace(path)

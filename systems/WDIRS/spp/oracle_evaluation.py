"""Isolated ground-truth oracle track for paper evaluation only.

Nothing in deployable synthesis imports this module.  The oracle consumes a
checksum of an already-frozen decision artifact and writes to a separate output
directory. Enumeration tokens are reported, never charged to deployment.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class OracleConfigResult:
    config_id: str
    construction_tokens: int
    per_query_error: Mapping[str, float]
    enumeration_tokens: int = 0
    enumeration_seconds: float = 0.0

    @property
    def mean_error(self) -> float:
        values = list(self.per_query_error.values())
        return sum(values) / len(values) if values else float("nan")


@dataclass(frozen=True)
class OracleReferences:
    frozen_deployment_sha256: str
    best_single_config_id: str
    best_single_error: float
    budgeted_selected_config_ids: Tuple[str, ...]
    budgeted_query_to_config: Mapping[str, str]
    budgeted_mean_error: float
    per_query_oracle_error: float
    enumeration_tokens: int
    enumeration_seconds: float


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _best_single(results: Sequence[OracleConfigResult]) -> OracleConfigResult:
    if not results:
        raise ValueError("oracle requires at least one configuration result")
    return min(results, key=lambda result: (result.mean_error, result.config_id))


def _per_query_oracle(results: Sequence[OracleConfigResult]) -> float:
    query_ids = sorted({qid for result in results for qid in result.per_query_error})
    if not query_ids:
        return float("nan")
    return sum(
        min(result.per_query_error.get(qid, 1.0) for result in results)
        for qid in query_ids
    ) / len(query_ids)


def solve_exact_budgeted_oracle(
    results: Sequence[OracleConfigResult], token_budget: int
) -> Tuple[Tuple[str, ...], Dict[str, str], float]:
    """Solve the exact query-routing portfolio ILP with SciPy/HiGHS."""
    try:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import lil_matrix
    except ImportError as exc:  # pragma: no cover - dependency is in requirements
        raise RuntimeError("scipy.optimize.milp is required for oracle ILP") from exc

    configs = list(results)
    query_ids = sorted({qid for result in configs for qid in result.per_query_error})
    n_configs, n_queries = len(configs), len(query_ids)
    # Variables: x_c (materialized), followed by y_qc (query routed to config).
    n_vars = n_configs + n_queries * n_configs
    objective = np.zeros(n_vars)
    for q_index, query_id in enumerate(query_ids):
        for c_index, result in enumerate(configs):
            y_index = n_configs + q_index * n_configs + c_index
            objective[y_index] = result.per_query_error.get(query_id, 1.0)

    rows = 1 + n_queries + n_queries * n_configs
    matrix = lil_matrix((rows, n_vars), dtype=float)
    lower = np.full(rows, -np.inf)
    upper = np.full(rows, np.inf)
    row = 0
    for c_index, result in enumerate(configs):
        matrix[row, c_index] = result.construction_tokens
    upper[row] = token_budget
    row += 1
    # Exactly one route per query.
    for q_index in range(n_queries):
        for c_index in range(n_configs):
            matrix[row, n_configs + q_index * n_configs + c_index] = 1.0
        lower[row] = upper[row] = 1.0
        row += 1
    # y_qc <= x_c.
    for q_index in range(n_queries):
        for c_index in range(n_configs):
            matrix[row, n_configs + q_index * n_configs + c_index] = 1.0
            matrix[row, c_index] = -1.0
            upper[row] = 0.0
            row += 1

    solution = milp(
        c=objective,
        integrality=np.ones(n_vars),
        bounds=Bounds(np.zeros(n_vars), np.ones(n_vars)),
        constraints=LinearConstraint(matrix.tocsr(), lower, upper),
        options={"time_limit": 600},
    )
    if not solution.success or solution.x is None:
        raise RuntimeError(f"budgeted oracle ILP failed: {solution.message}")
    selected = tuple(
        sorted(
            configs[index].config_id
            for index in range(n_configs)
            if solution.x[index] >= 0.5
        )
    )
    routing: Dict[str, str] = {}
    errors: List[float] = []
    for q_index, query_id in enumerate(query_ids):
        routed_index = max(
            range(n_configs),
            key=lambda c_index: solution.x[
                n_configs + q_index * n_configs + c_index
            ],
        )
        routing[query_id] = configs[routed_index].config_id
        errors.append(configs[routed_index].per_query_error.get(query_id, 1.0))
    return selected, routing, sum(errors) / len(errors)


def build_oracle_references(
    results: Sequence[OracleConfigResult],
    *,
    token_budget: int,
    frozen_deployment_manifest: Path,
) -> OracleReferences:
    """Compute references only after the deployable decision is frozen."""
    manifest_path = Path(frozen_deployment_manifest)
    seal_path = manifest_path.parent / "SEALED"
    if not manifest_path.exists() or not seal_path.exists():
        raise ValueError("deployment artifact must be sealed before oracle evaluation")
    if seal_path.read_text().strip() != file_sha256(manifest_path):
        raise ValueError("deployment artifact changed after it was sealed")
    best = _best_single(results)
    selected, routing, budgeted_error = solve_exact_budgeted_oracle(
        results, token_budget
    )
    return OracleReferences(
        frozen_deployment_sha256=file_sha256(manifest_path),
        best_single_config_id=best.config_id,
        best_single_error=best.mean_error,
        budgeted_selected_config_ids=selected,
        budgeted_query_to_config=routing,
        budgeted_mean_error=budgeted_error,
        per_query_oracle_error=_per_query_oracle(results),
        enumeration_tokens=sum(result.enumeration_tokens for result in results),
        enumeration_seconds=sum(result.enumeration_seconds for result in results),
    )


def save_oracle_references(
    references: OracleReferences, output_path: Path
) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(references), indent=2))
    tmp.replace(path)

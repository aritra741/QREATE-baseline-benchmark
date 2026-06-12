"""Typed action space for the meta-controller agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

META_SOLVER_ACTIONS = frozenset(
    {
        "use_greedy",
        "use_bo_tpe",
        "use_hyperband",
        "use_coordinate_descent",
        "use_ilp",
        "use_clustered_routing",
    }
)

META_ACTIONS = META_SOLVER_ACTIONS | frozenset({"finalize", "probe_more"})

ACTION_TO_STAGE3_ALGORITHM: dict[str, str | None] = {
    "use_greedy": "greedy",
    "use_bo_tpe": "bayesian_opt",
    "use_hyperband": "hyperband",
    "use_coordinate_descent": "coord_descent",
    "use_ilp": "ilp",
    "use_clustered_routing": None,
    "probe_more": None,
    "finalize": None,
}

STAGE3_ALGORITHM_TO_ACTION: dict[str, str] = {
    v: k for k, v in ACTION_TO_STAGE3_ALGORITHM.items() if v is not None
}

ACTION_LABELS: dict[str, str] = {
    "use_greedy": "Greedy ranking under budget",
    "use_bo_tpe": "Bayesian optimization / TPE search",
    "use_hyperband": "Hyperband multi-fidelity search",
    "use_coordinate_descent": "Coordinate descent on config axes",
    "use_ilp": "Integer linear programming assignment",
    "use_clustered_routing": "Cluster-conditioned routing assignment",
    "probe_more": "Probe additional configurations",
    "finalize": "Finalize selected solver family",
}


@dataclass
class MetaActionRecord:
    action: str
    rationale_code: str
    confidence: float
    expected_gain: float
    budget_impact: int
    observation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

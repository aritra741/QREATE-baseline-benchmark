"""Repair-agent contracts. Gold paths stay out of this package."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


IssueKind = Literal[
    "empty_query",
    "join_yield",
    "dtype_coercion",
    "domain",
    "coverage",
    "provenance",
    "constraint",
    "high_null",
]

ActionName = Literal[
    "reextract_failed_cells",
    "reextract_attribute_slice",
    "normalize_to_declared_domain",
    "repair_join_vocabulary",
    "compare_extractors",
    "adjudicate_disagreement",
]


@dataclass
class RepairIssue:
    kind: IssueKind
    attributes: list[str]
    query_ids: list[str]
    severity: float
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class Repair:
    action: ActionName
    issue: RepairIssue
    estimated_cost: int
    priority: float
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectorSnapshot:
    empty_query_ids: list[str]
    join_yield: dict[str, float]
    coercion_count: int
    high_null: dict[str, float]
    domain_disjoint: list[str]
    coverage_gaps: list[str]
    provenance_gaps: int
    constraint_failures: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "empty_query_count": len(self.empty_query_ids),
            "empty_query_ids": list(self.empty_query_ids),
            "join_yield": dict(self.join_yield),
            "coercion_count": self.coercion_count,
            "high_null": dict(self.high_null),
            "domain_disjoint": list(self.domain_disjoint),
            "coverage_gaps": list(self.coverage_gaps),
            "provenance_gaps": self.provenance_gaps,
            "constraint_failures": self.constraint_failures,
        }


@dataclass
class RepairReport:
    stopped: str
    before: dict[str, Any]
    after: dict[str, Any]
    steps: list[dict[str, Any]]
    tokens_spent: int
    bugfix_log: list[dict[str, Any]]
    routing: dict[str, str]
    shared_er: dict[str, Any] = field(default_factory=dict)

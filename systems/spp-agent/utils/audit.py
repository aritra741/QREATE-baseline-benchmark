from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AuditLog:
    run_id: str
    timestamp: str
    token_budget_initial: int

    probe_config_ids: list[str] = field(default_factory=list)
    probe_expanded: bool = False
    probe_n_judge_pairs: int = 0
    probe_total_token_cost: float = 0.0

    n_clusters: int = 0
    cluster_types: dict[int, str] = field(default_factory=dict)
    cluster_sizes: dict[int, int] = field(default_factory=dict)
    cluster_labels: list[int] = field(default_factory=list)

    cluster_btl_scores: dict[int, dict[str, float]] = field(default_factory=dict)
    cluster_btl_uncertainty: dict[int, dict[str, float]] = field(default_factory=dict)

    cluster_surrogate_loo_rhos: dict[int, dict[str, float]] = field(default_factory=dict)
    cluster_selected_surrogates: dict[int, str] = field(default_factory=dict)

    agent_actions: list[dict[str, Any]] = field(default_factory=list)

    routing_table: dict[int, str] = field(default_factory=dict)
    selected_configs: list[str] = field(default_factory=list)
    risk_level: str = "risk_neutral"
    n_materializations: int = 0
    token_budget_spent: int = 0
    token_budget_remaining: int = 0

    used_fallback: bool = False
    fallback_reason: str = ""

    @classmethod
    def new(cls, token_budget_initial: int) -> AuditLog:
        return cls(
            run_id=str(uuid.uuid4()),
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            token_budget_initial=token_budget_initial,
        )

    def log_action(
        self,
        turn: int,
        thought: str,
        action: str,
        action_input: dict,
        observation: dict,
    ) -> None:
        summary = str(observation)[:300]
        self.agent_actions.append(
            {
                "turn": turn,
                "thought": thought,
                "action": action,
                "action_input": action_input,
                "observation_summary": summary,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def save_audit_log(log: AuditLog, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log.to_dict(), indent=2), encoding="utf-8")

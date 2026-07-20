"""Shared-work operator DAG and exact marginal token accounting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Set, Tuple


@dataclass(frozen=True)
class OperatorNode:
    node_id: str
    stage: str
    upper_bound_tokens: int
    dependencies: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.upper_bound_tokens < 0:
            raise ValueError("operator token cost cannot be negative")


class SharedOperatorDAG:
    def __init__(
        self,
        nodes: Iterable[OperatorNode],
        config_terminals: Mapping[str, Iterable[str]],
    ):
        node_list = list(nodes)
        self.nodes: Dict[str, OperatorNode] = {
            node.node_id: node for node in node_list
        }
        self.config_terminals = {
            config_id: tuple(terminals)
            for config_id, terminals in config_terminals.items()
        }
        if len(self.nodes) != len(node_list):
            raise ValueError("duplicate operator node IDs")
        self._validate()

    def _validate(self) -> None:
        for node in self.nodes.values():
            missing = set(node.dependencies) - set(self.nodes)
            if missing:
                raise ValueError(
                    f"operator {node.node_id} has missing dependencies: {missing}"
                )
        for config_id, terminals in self.config_terminals.items():
            missing = set(terminals) - set(self.nodes)
            if missing:
                raise ValueError(
                    f"config {config_id} has missing terminal operators: {missing}"
                )
        visiting: Set[str] = set()
        visited: Set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError("operator graph contains a cycle")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in self.nodes[node_id].dependencies:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in self.nodes:
            visit(node_id)

    def closure_for_config(self, config_id: str) -> Set[str]:
        if config_id not in self.config_terminals:
            raise KeyError(config_id)
        closure: Set[str] = set()

        def include(node_id: str) -> None:
            if node_id in closure:
                return
            closure.add(node_id)
            for dependency in self.nodes[node_id].dependencies:
                include(dependency)

        for terminal in self.config_terminals[config_id]:
            include(terminal)
        return closure

    def closure_for_portfolio(self, config_ids: Iterable[str]) -> Set[str]:
        closure: Set[str] = set()
        for config_id in config_ids:
            closure |= self.closure_for_config(config_id)
        return closure

    def cost(self, config_ids: Iterable[str]) -> int:
        return sum(
            self.nodes[node_id].upper_bound_tokens
            for node_id in self.closure_for_portfolio(config_ids)
        )

    def marginal_cost(self, config_id: str, selected: Set[str]) -> int:
        before = self.closure_for_portfolio(selected)
        after = before | self.closure_for_config(config_id)
        return sum(
            self.nodes[node_id].upper_bound_tokens for node_id in after - before
        )

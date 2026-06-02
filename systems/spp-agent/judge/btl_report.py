from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def _connected_components(config_ids: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    parent = {cid: cid for cid in config_ids}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a, b in edges:
        if a in parent and b in parent:
            union(a, b)

    groups: dict[str, list[str]] = defaultdict(list)
    for cid in config_ids:
        groups[find(cid)].append(cid)
    return [sorted(group) for group in groups.values()]


def build_btl_report(
    comparisons: list[dict],
    config_ids: list[str],
    btl_scores: dict[str, float],
) -> dict:
    win_counts: dict[str, int] = {cid: 0 for cid in config_ids}
    loss_counts: dict[str, int] = {cid: 0 for cid in config_ids}
    tie_counts: dict[str, int] = {cid: 0 for cid in config_ids}
    win_matrix: dict[str, dict[str, int]] = {a: {b: 0 for b in config_ids} for a in config_ids}
    comparison_edges: list[dict] = []

    for comp in comparisons:
        winner = comp.get("winner")
        loser = comp.get("loser")
        if not winner or not loser:
            continue
        comparison_edges.append({"winner": winner, "loser": loser})
        if winner in win_counts:
            win_counts[winner] += 1
        if loser in loss_counts:
            loss_counts[loser] += 1
        if winner in win_matrix and loser in win_matrix[winner]:
            win_matrix[winner][loser] += 1

    undirected_edges = [(e["winner"], e["loser"]) for e in comparison_edges]
    components = _connected_components(config_ids, undirected_edges)
    compared_configs = {cid for edge in undirected_edges for cid in edge}
    isolated = [cid for cid in config_ids if cid not in compared_configs]

    return {
        "win_counts": win_counts,
        "loss_counts": loss_counts,
        "tie_counts": tie_counts,
        "win_matrix": win_matrix,
        "comparison_edges": comparison_edges,
        "comparison_graph_connected": len(components) == 1,
        "num_components": len(components),
        "components": components,
        "isolated_configs": isolated,
        "btl_scores": btl_scores,
    }


def log_btl_report(report: dict, logger) -> None:
    logger.info("BTL comparison graph connected=%s components=%d", report["comparison_graph_connected"], report["num_components"])
    if report["isolated_configs"]:
        logger.warning("Configs with no judge comparisons: %s", report["isolated_configs"])
    for cid in sorted(report["win_counts"]):
        logger.info(
            "  %s wins=%d losses=%d btl=%.6f",
            cid,
            report["win_counts"][cid],
            report["loss_counts"][cid],
            report["btl_scores"].get(cid, float("nan")),
        )
    logger.info("Comparison edges (%d):", len(report["comparison_edges"]))
    for edge in report["comparison_edges"]:
        logger.info("  %s > %s", edge["winner"], edge["loser"])

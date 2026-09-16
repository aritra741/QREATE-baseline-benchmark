from __future__ import annotations

from quwarts.core.conflict import cluster_templates
from quwarts.core.models import Configuration
from quwarts.core.population import policy_from_demands
from quwarts.core.route import route_workload
from quwarts.core.search import generate_candidates, select_portfolio
from quwarts.core.workload import analyze_workload


def test_static_route_is_deterministic() -> None:
    logical, workload = analyze_workload(
        {
            "q0": "SELECT player.name FROM player WHERE player.position = 'Guard'",
            "q1": "SELECT player.name FROM player WHERE player.position = 'Forward'",
        }
    )
    clusters = cluster_templates(workload)
    pops = {cluster.id: policy_from_demands(cluster.resolved_demands, workload) for cluster in clusters}
    configs = generate_candidates(logical, workload, clusters, pops)
    assert configs
    cluster_map = {tid: cluster.id for cluster in clusters for tid in cluster.template_ids}
    a = route_workload(workload, configs, [], cluster_map)
    b = route_workload(workload, configs, [], cluster_map)
    assert a == b
    assert a.get("q0") == a.get("q1")


def test_adding_config_does_not_reroute() -> None:
    logical, workload = analyze_workload(
        {"q0": "SELECT player.name FROM player WHERE player.position = 'Guard'"}
    )
    clusters = cluster_templates(workload)
    pops = {cluster.id: policy_from_demands(cluster.resolved_demands, workload) for cluster in clusters}
    configs = generate_candidates(logical, workload, clusters, pops)
    cluster_map = {tid: cluster.id for cluster in clusters for tid in cluster.template_ids}
    first = route_workload(workload, configs[:1], [], cluster_map)
    second = route_workload(workload, configs, [], cluster_map)
    assert first["q0"] == second["q0"]


def test_portfolio_covers_each_cluster() -> None:
    logical, workload = analyze_workload(
        [
            "SELECT player.name FROM player WHERE player.position = 'Guard'",
            "SELECT AVG(player.salary) FROM player",
        ]
    )
    clusters = cluster_templates(workload)
    pops = {cluster.id: policy_from_demands(cluster.resolved_demands, workload) for cluster in clusters}
    configs = generate_candidates(logical, workload, clusters, pops)
    utilities = {config.id: 0.5 for config in configs}
    costs = {config.id: 1.0 for config in configs}
    selected = select_portfolio(configs, utilities, costs, clusters, theta_remaining=100)
    covered = {config.cluster_id for config in selected}
    assert covered == {cluster.id for cluster in clusters}

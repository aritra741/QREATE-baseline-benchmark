from __future__ import annotations

from quwarts.core.amplify import amp, amp_role
from quwarts.core.models import AttributeRequirement, Role
from quwarts.core.pilot import estimate_rho_from_disagreement, synthetic_stats


def test_amp_roles_on_known_statistics() -> None:
    stats = synthetic_stats(n_rows=100, n_groups=10, n_distinct=20, rho=0.25, n_scored_columns=4)
    assert amp_role(Role.PROJECT, stats) == 1.0
    assert amp_role(Role.KEY, stats) == 4.0
    assert amp_role(Role.GROUP, stats) == 20.0
    assert amp_role(Role.AGG_EXTREMAL, stats) == 10.0
    assert amp_role(Role.AGG_DISTINCT, stats) == 5.0
    additive = amp_role(Role.AGG_ADDITIVE, stats)
    assert 0 < additive <= 1


def test_amp_takes_max_role_times_freq() -> None:
    stats = synthetic_stats(n_rows=100, n_groups=10, n_distinct=20, rho=0.25, n_scored_columns=4)
    req = AttributeRequirement(
        name="player.id",
        entity_type="player",
        dtype="string",
        roles={Role.KEY, Role.PROJECT},
        freq_weight=3.0,
        stats=stats,
    )
    assert req.amp is None
    assert amp(req) == 12.0


def test_rho_disagreement_estimator() -> None:
    values_a = ["a", "a", "b", "b", "c", "c"]
    values_b = ["a", "x", "b", "y", "c", "z"]
    clusters = ["u", "u", "v", "v", "w", "w"]
    rho = estimate_rho_from_disagreement(values_a, values_b, clusters)
    assert 0.0 <= rho <= 1.0

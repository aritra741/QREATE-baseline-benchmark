from __future__ import annotations

from quwarts.core.amplify import amp
from quwarts.core.models import AttributeRequirement, Role
from quwarts.core.pilot import synthetic_stats
from quwarts.core.quality import (
    CELL_CHANGE_STOP,
    RHO_VOTE_MAX,
    majority,
    route_count,
    _changed_fraction,
)


def test_route_count_follows_roles_and_amp() -> None:
    stats = synthetic_stats(n_rows=100, n_groups=10, n_distinct=20, rho=0.25, n_scored_columns=2)
    key = AttributeRequirement(
        name="e.id", entity_type="e", dtype="string",
        roles={Role.KEY}, freq_weight=1.0, stats=stats,
    )
    group = AttributeRequirement(
        name="e.g", entity_type="e", dtype="string",
        roles={Role.GROUP}, freq_weight=1.0, stats=stats,
    )
    project = AttributeRequirement(
        name="e.p", entity_type="e", dtype="string",
        roles={Role.PROJECT}, freq_weight=1.0, stats=stats,
    )
    assert route_count(key) == 3
    assert route_count(group) == (3 if amp(group) >= 2 else 2)
    assert route_count(project) == 1


def test_majority_folds_case_and_punctuation() -> None:
    assert majority(["France", "france.", "Germany"]) == "France"
    assert majority(["", None, "  "]) is None


def test_repair_stops_on_small_cell_change_not_nominal_fill() -> None:
    assert CELL_CHANGE_STOP == 0.02
    before = {("d1", "a"): "x", ("d2", "a"): None}
    after = {("d1", "a"): "x", ("d2", "a"): None}
    assert _changed_fraction(before, after) < CELL_CHANGE_STOP
    moved = {("d1", "a"): "y", ("d2", "a"): "z"}
    assert _changed_fraction(before, moved) > CELL_CHANGE_STOP


def test_rho_vote_threshold_is_not_a_score() -> None:
    assert RHO_VOTE_MAX == 0.5

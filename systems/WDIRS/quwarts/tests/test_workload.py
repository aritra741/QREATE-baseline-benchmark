from __future__ import annotations

from quwarts.core.models import TemplateShape
from quwarts.core.workload import analyze_workload, classify_shape, parse_sql


GOLDEN = {
    "filtered_projection": "SELECT player.name FROM player WHERE player.position = 'Guard'",
    "cross_attribute": "SELECT SUM(player.salary) FROM player WHERE player.position = 'Guard'",
    "unfiltered": "SELECT AVG(player.salary) FROM player",
    "count_star": "SELECT COUNT(*) FROM player",
    "anti_join": (
        "SELECT player.name FROM player WHERE player.team_id NOT IN "
        "(SELECT team.id FROM team WHERE team.city = 'Boston')"
    ),
    "same_attr_filter_agg": "SELECT SUM(player.salary) FROM player WHERE player.salary > 1000000",
}


def test_shape_classification() -> None:
    assert classify_shape(parse_sql(GOLDEN["filtered_projection"])) == (
        TemplateShape.FILTERED_PROJECTION,
        True,
    )
    assert classify_shape(parse_sql(GOLDEN["cross_attribute"]))[0] == TemplateShape.CROSS_ATTRIBUTE_FILTER
    assert classify_shape(parse_sql(GOLDEN["unfiltered"])) == (
        TemplateShape.UNFILTERED_AGGREGATE,
        False,
    )
    assert classify_shape(parse_sql(GOLDEN["count_star"])) == (
        TemplateShape.BASE_CARDINALITY,
        False,
    )
    assert classify_shape(parse_sql(GOLDEN["anti_join"])) == (
        TemplateShape.ANTI_JOIN,
        False,
    )
    shape, safe = classify_shape(parse_sql(GOLDEN["same_attr_filter_agg"]))
    assert shape == TemplateShape.FILTERED_AGGREGATE
    assert safe is True


def test_unknown_is_slice_unsafe() -> None:
    shape, safe = classify_shape(parse_sql("SELECT 1"))
    assert safe is False
    assert shape in {TemplateShape.UNKNOWN, TemplateShape.UNFILTERED_AGGREGATE}


def test_templating_collapses_constants() -> None:
    _, workload = analyze_workload(
        [
            "SELECT player.name FROM player WHERE player.position = 'Guard'",
            "SELECT player.name FROM player WHERE player.position = 'Forward'",
        ]
    )
    assert len(workload.templates) == 1
    template = workload.templates[0]
    assert template.freq == 2
    slot = template.param_slots[0]
    assert set(slot.observed_constants) == {"Guard", "Forward"}
    assert "player.position" in template.roles_by_attribute


def test_roles_and_slices() -> None:
    _, workload = analyze_workload(
        ["SELECT SUM(player.salary) FROM player WHERE player.position = 'Guard'"]
    )
    req = workload.requirements["player.salary"]
    assert req.slice.kind in {"ranges", "full"}
    assert req.freq_weight >= 1
    pred = workload.requirements["player.position"]
    assert pred.slice.kind == "ranges"

from __future__ import annotations

from quwarts.core.router.comparator import need_score, value_score
from quwarts.core.router.needs import Need, can_serve, query_needs

ATTRS = {"legal": {"verdict", "hearing_year", "first_judge", "case_type"}, "p": {"team", "age"}, "t": {"team_name"}}


def by_attr(needs):
    return {need.attribute: need for need in needs}


def test_value_versus_predicate_needs():
    sql = "SELECT first_judge, AVG(hearing_year) FROM legal WHERE verdict = 'Dismissed' GROUP BY first_judge"
    needs = by_attr(query_needs("q", sql, ATTRS))
    assert needs["verdict"].kind == "predicate" and needs["verdict"].conditions == ("verdict = 'Dismissed'",)
    assert needs["first_judge"].kind == "value" and needs["hearing_year"].kind == "value"
    assert abs(sum(n.weight for n in needs.values()) - 1.0) < 1e-9


def test_case_conditions_are_predicates_and_mixed_use_is_value():
    sql = ("SELECT CASE WHEN case_type LIKE '%Civil%' THEN 'civil' ELSE 'other' END AS k, COUNT(*) "
           "FROM legal WHERE hearing_year > 2005 GROUP BY k")
    needs = by_attr(query_needs("q", sql, ATTRS))
    assert needs["case_type"].kind == "predicate" and needs["hearing_year"].kind == "predicate"
    sql2 = "SELECT verdict, COUNT(*) FROM legal WHERE verdict != 'Others' GROUP BY verdict"
    assert by_attr(query_needs("q", sql2, ATTRS))["verdict"].kind == "value"


def test_join_columns_are_value_needs():
    sql = "SELECT t.team_name, AVG(p.age) FROM p JOIN t ON TRIM(p.team) = TRIM(t.team_name) GROUP BY t.team_name"
    needs = {n.qualified: n for n in query_needs("q", sql, ATTRS)}
    assert needs["p.team"].kind == "value" and needs["t.team_name"].kind == "value"


def test_information_order():
    value = Need("a", "legal", "verdict", "value")
    pred = Need("b", "legal", "verdict", "predicate", ("verdict = 'Dismissed'",))
    other = Need("c", "legal", "verdict", "predicate", ("verdict = 'Approved'",))
    assert can_serve(value, pred) and can_serve(None, pred)
    assert not can_serve(pred, value) and not can_serve(pred, other) and can_serve(pred, pred)


def test_predicate_need_scores_condition_truth_only():
    pred = Need("b", "legal", "verdict", "predicate", ("verdict = 'Dismissed'",))
    assert need_score(pred, "Approved", "Others", "str") == 1.0  # both FALSE: the query cannot tell them apart
    assert need_score(pred, "Dismissed", "Approved", "str") == 0.0
    assert need_score(pred, None, None, "str") == 1.0
    year = Need("b", "legal", "hearing_year", "predicate", ("hearing_year > 2005",))
    assert need_score(year, "2008", 2010, "int") == 1.0 and need_score(year, 2001, "2010", "int") == 0.0


def test_value_score_matches_benchmark_rules():
    assert value_score("Painting ||", "Painting", "multi_str") == 1.0
    assert abs(value_score("Painting || Sculpture", "Painting", "multi_str") - 2 / 3) < 1e-9
    assert value_score("1,000", 1000, "int") == 1.0 and value_score("EY", "ey", "str") == 1.0
    assert value_score(None, "", "str") == 1.0 and value_score(None, "x", "str") == 0.0


def test_undescribed_attributes_and_aliases():
    sql = ("SELECT CASE WHEN net > 0 THEN 'p' ELSE 'l' END AS status, AVG(total_debt) FROM finance "
           "WHERE net IS NOT NULL GROUP BY status")
    needs = by_attr(query_needs("q", sql, {"finance": {"net"}}))
    assert set(needs) == {"net", "total_debt"}  # total_debt is not described but is needed; status is an alias

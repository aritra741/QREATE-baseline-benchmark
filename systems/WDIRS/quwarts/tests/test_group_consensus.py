from __future__ import annotations

from quwarts.core.group_consensus import (
    accept_majority,
    accept_unanimous,
    canonical_expr_id,
    query_votes_for_key,
    role_canonicalize,
    stable_row_key,
)
from quwarts.core.group_replay import is_sql_null


def test_role_canonicalize_drops_aliases() -> None:
    left = role_canonicalize(
        "CASE WHEN LOWER(d.manufacturer) <> '' THEN 'known' ELSE 'unknown' END",
        {"d": "drug"},
        "drug",
    )
    right = role_canonicalize(
        "CASE WHEN LOWER(manufacturer) <> '' THEN 'known' ELSE 'unknown' END",
        {"drug": "drug"},
        "drug",
    )
    assert left == right
    assert canonical_expr_id(
        "CASE WHEN LOWER(d.manufacturer) <> '' THEN 'known' ELSE 'unknown' END",
        {"d": "drug"},
        "drug",
    ) == canonical_expr_id(
        "CASE WHEN LOWER(dr.manufacturer) <> '' THEN 'known' ELSE 'unknown' END",
        {"dr": "drug"},
        "drug",
    )


def test_stable_row_uses_participating_table_only() -> None:
    key = stable_row_key(
        "CASE WHEN manufacturer <> '' THEN 'known' ELSE 'unknown' END",
        {"dr": "drug", "i": "institution"},
        "drug",
        ["dr", "i"],
        "35|9",
    )
    assert key == "drug:35"


def test_internal_conflict_abstains() -> None:
    site = {
        "canonical_key": "abcd|drug:1",
        "query_id": "q1",
        "official_expr_id": "e",
        "witness_key": "1",
    }
    votes = [
        {"query_id": "q1", "expr_id": "e", "witness_key": "1", "resolved": True, "agreement": "majority", "group_value": "known"},
        {"query_id": "q1", "expr_id": "e", "witness_key": "1", "resolved": True, "agreement": "majority", "group_value": "unknown"},
    ]
    index = {("q1", "e", "1"): site}
    out = query_votes_for_key(votes, index)
    assert out["abcd|drug:1"]["abstain"] == ["q1"]
    assert out["abcd|drug:1"]["votes"] == {}


def test_one_query_one_vote_and_unanimous_needs_two() -> None:
    sites = [
        {"allowed": ["known", "unknown", None], "canonical_key": "k"},
        {"allowed": ["known", "unknown", None], "canonical_key": "k"},
    ]
    one = {"votes": {"q1": "known"}, "abstain": [], "n_queries": 1}
    two = {"votes": {"q1": "known", "q2": "known"}, "abstain": [], "n_queries": 2}
    assert accept_unanimous(one, sites) is None
    assert accept_unanimous(two, sites) == "known"
    assert accept_unanimous({"votes": {"q1": "known", "q2": "unknown"}, "abstain": []}, sites) is None


def test_majority_requires_three_two_thirds_and_margin() -> None:
    sites = [{"allowed": ["a", "b", None]}] * 3
    split = {"votes": {"q1": "a", "q2": "a", "q3": "b"}, "abstain": []}
    sweep = {"votes": {"q1": "a", "q2": "a", "q3": "a"}, "abstain": []}
    assert accept_majority(split, sites) is None
    assert accept_majority(sweep, sites) == "a"
    assert accept_majority({"votes": {"q1": "a", "q2": "a"}, "abstain": []}, sites) is None
    assert not is_sql_null("a")

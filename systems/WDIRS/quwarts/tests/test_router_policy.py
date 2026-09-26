from __future__ import annotations

import json
import sqlite3

import pytest

from quwarts.core.router.plan import build_plan
from quwarts.core.router.policy import Decision, extractiveness_prior, fit_budget, repair_decision, route_decision
from quwarts.core.router.probes import fake_caller_factory
from quwarts.core.router.registry import CorpusSpec, TableSpec
from quwarts.core.router.residue import residue_features
from quwarts.core.router.workload_features import AttributeUse, workload_features

from tests.test_router_probes import responder, toy_spec


def use(name="a", **kw) -> AttributeUse:
    base = dict(table="t", name=name, dtype="string", roles=["predicate"], query_ids=["q1", "q2"])
    base.update(kw)
    return AttributeUse(**base)


def table(lam=0.5):
    return {"context_fit_lambda": lam, "label_surface": {}, "full_read_cost": 1000, "window_read_cost": 400}


def test_repair_needs_small_residue_and_trusted_incumbent():
    ok = {"present": True, "residue_rows": 3, "residue_fraction": 0.03, "incumbent_trust": 0.9, "incumbent_trust_kind": "grounding"}
    assert repair_decision(use(), ok).route == "repair"
    assert repair_decision(use(), {**ok, "residue_fraction": 0.4}) is None
    assert repair_decision(use(), {**ok, "incumbent_trust": 0.1}) is None
    assert repair_decision(use(), {**ok, "incumbent_trust": None}) is None
    assert repair_decision(use(), None) is None


@pytest.mark.parametrize(
    "lam,probe,route",
    [
        (3.0, {"g": 0.9, "delta": 0.0}, "program"),            # long docs, shareable span
        (0.5, {"g": 0.9, "delta": 0.0, "r": 0.8}, "program"),  # fits, stable anchor
        (0.5, {"g": 0.9, "delta": 0.0, "r": 0.2}, "canonical_map"),
        (0.5, {"g": 0.9, "delta": 0.0}, "canonical_map"),      # no anchor evidence
        (0.5, {"g": 0.9, "delta": 0.6}, "fused_map"),          # span but query-dependent
        (0.5, {"g": 0.1, "delta": 0.0}, "fused_map"),          # interpretive
        (3.0, {"g": 0.1, "delta": 0.0}, "retrieval_map"),
    ],
)
def test_route_matrix(lam, probe, route):
    assert route_decision(use(), table(lam), probe).route == route


def test_priors_without_probe():
    assert extractiveness_prior(use("hearing_year", dtype="numeric"), None)[0] == "extractive"
    assert extractiveness_prior(use("legal_basis_num", dtype="numeric"), None)[0] == "interpretive"
    assert extractiveness_prior(use("verdict", closed_label=True), 0.0)[0] == "interpretive"
    assert extractiveness_prior(use("verdict", closed_label=True), 1.0)[0] == "extractive"
    assert extractiveness_prior(use("auditor", description="name of the audit firm"), None)[0] == "extractive"
    assert extractiveness_prior(use("company_id"), None)[0] == "extractive"
    assert extractiveness_prior(use("valid_flag"), None)[0] == "interpretive"


def test_fit_budget_drops_lowest_value_queries_first():
    decisions = [
        Decision("t.a", "t", "fused_map", "R3", query_ids=["q1", "q2", "q3", "q4"]),
        Decision("t.b", "t", "fused_map", "R3", query_ids=["q1", "q2"]),
    ]
    out = fit_budget(decisions, {"t": table()}, {"t": ["q1", "q2", "q3", "q4"]}, available=1000)
    assert out["fits"] and out["costs"]["total"] <= 1000
    assert sorted(out["map_queries"]["t:fused_map"]) == ["q1", "q2"]  # q1, q2 carry two attributes
    assert decisions[0].evidence["kept_queries"] == ["q3", "q4"]


def test_fit_budget_keeps_when_nothing_is_affordable():
    decisions = [Decision("t.a", "t", "fused_map", "R3", query_ids=["q1"])]
    out = fit_budget(decisions, {"t": table()}, {"t": ["q1"]}, available=10)
    assert decisions[0].route == "keep" and out["fits"]


def test_residue_counts_sql_unknown_rows_only_inside_support(tmp_path):
    spec = toy_spec(tmp_path)
    db = tmp_path / "inc.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE c (doc_id TEXT, hearing_year TEXT, verdict TEXT)")
    rows = [(f"{i}.txt", str(2000 + i) if i != 5 else None, "Dismissed" if i % 2 else None) for i in range(1, 9)]
    conn.executemany("INSERT INTO c VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()
    out = residue_features(spec, workload_features(spec), db)
    year = out["attributes"]["c.hearing_year"]
    assert year["residue_rows"] == 1 and year["incumbent_trust"] == 1.0
    # verdict is NULL on rows 2,4,6,8; all are inside support (hearing_year known > 2003 or grouped).
    assert out["attributes"]["c.verdict"]["residue_rows"] == 4


def test_plan_is_deterministic_and_probe_is_journaled(tmp_path):
    spec = toy_spec(tmp_path)
    build = fake_caller_factory(responder)
    first = build_plan(spec, theta=400_000, caller=build(400_000), journal=tmp_path / "j1.jsonl")
    second = build_plan(spec, theta=400_000, caller=build(400_000), journal=tmp_path / "j2.jsonl")
    assert first["plan_hash"] == second["plan_hash"]
    routes = {d["qualified"]: d["route"] for d in first["decisions"]}
    assert routes["c.verdict"] == "fused_map"      # query-dependent label
    assert routes["c.hearing_year"] in {"program", "canonical_map"}
    assert first["budget"]["probe_spent"] <= first["budget"]["probe_budget"]
    assert (tmp_path / "j1.jsonl").read_text().strip()


def test_cli_blocks_gold_reads(tmp_path):
    import builtins
    import importlib

    import quwarts.eval.router_plan as cli

    importlib.reload(cli)
    gold = tmp_path / "ground_truth" / "x.json"
    gold.parent.mkdir()
    gold.write_text("{}")
    try:
        with pytest.raises(PermissionError):
            open(gold)
    finally:
        builtins.open = cli._ORIGINAL_OPEN


def test_parse_split_sql():
    from quwarts.core.router.registry import parse_split_sql

    text = "-- Query 1: test (agg_only) id=a1\nSELECT 1\nFROM t;\n\n-- Query 2: test (x) id=b2\nSELECT 2;\n"
    assert parse_split_sql(text) == {"a1": "SELECT 1 FROM t", "b2": "SELECT 2"}


def test_recall_gap_routes_to_query_conditioned_reads_when_affordable():
    probe = {"g": 0.9, "delta": 0.0, "r": 0.9, "recall_gap": 0.5}
    assert route_decision(use(), table(0.5), probe).route == "fused_map"
    assert route_decision(use(), table(3.0), probe).route == "program"  # long documents: cannot afford maps


def test_fit_budget_finds_combination_greedy_missed():
    # The CSPaper v1 failure: one canonical bundle plus one fused slot slightly exceed
    # the budget; greedy dropped every fused slot. The exact fit trades instead.
    decisions = [Decision(f"t.c{i}", "t", "canonical_map", "R2'", query_ids=["q9"]) for i in range(2)]
    decisions.append(Decision("t.f", "t", "fused_map", "R3", query_ids=["q1", "q2", "q3", "q4", "q5"]))
    out = fit_budget(decisions, {"t": table()}, {"t": []}, available=1500)
    assert out["served_value"] == 2 and out["fits"]  # only one 1000-token item fits; both are worth 2 uses
    out = fit_budget(
        [Decision("t.c", "t", "canonical_map", "R2'", query_ids=["q9"]),
         Decision("t.f", "t", "fused_map", "R3", query_ids=["q1", "q2", "q3"])],
        {"t": table()}, {"t": []}, available=1000,
    )
    assert out["served_value"] == 2  # fused slot for q1,q2 (2 uses) instead of the bundle (1 use)

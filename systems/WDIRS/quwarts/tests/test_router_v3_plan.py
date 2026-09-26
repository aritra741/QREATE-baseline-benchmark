from __future__ import annotations

import math

from quwarts.core.router.context_probe import Observations, FieldSpec
from quwarts.core.router.facility import INCUMBENT, combine, need_distances, table_frontier
from quwarts.core.router.needs import CANONICAL, Need
from quwarts.core.router.plan_v3 import build_plan_v3
from quwarts.core.router.probes import fake_caller_factory

from tests.test_router_context_probe import responder
from tests.test_router_probes import toy_spec


def needs_and_obs(agree: bool):
    a = Need("q1", "t", "x", "value", weight=1.0)
    b = Need("q2", "t", "x", "value", weight=1.0)
    obs = Observations()
    for i in range(10):
        doc = f"{i}.txt"
        obs.add("t", doc, "q1", {"x": f"v{i}"})
        obs.add("t", doc, "q2", {"x": f"v{i}" if agree else f"w{i}"})
        obs.add("t", doc, CANONICAL, {"x": f"v{i}"})
    return [a, b], obs


FIELDS = {"t.x": FieldSpec("x", "str", "")}


def test_agreeing_contexts_share_one_column():
    needs, obs = needs_and_obs(agree=True)
    d = need_distances(needs, obs, FIELDS, {})
    assert d[("q1|t.x", "q2")].mean == 0.0 and d[("q1|t.x", INCUMBENT)].mean == 1.0
    frontier = table_frontier("t", needs, d, read_cost=100)
    cost, loss, picks = combine({"t": frontier}, budget=100)
    assert cost == 100 and len(picks["t"].contexts) == 1  # one read serves both queries
    assert loss < 0.5


def test_disagreeing_contexts_split_the_column():
    needs, obs = needs_and_obs(agree=False)
    d = need_distances(needs, obs, FIELDS, {})
    frontier = table_frontier("t", needs, d, read_cost=100)
    _cost, loss, picks = combine({"t": frontier}, budget=200)
    # q2 must have its own read; q1 is served by its own read or by the canonical read (they agree).
    assert "q2" in picks["t"].contexts and len(picks["t"].contexts) == 2 and loss == 0.0
    # With budget for one read, the other query keeps the (null) incumbent: loss 1 for it.
    _c, loss1, picks1 = combine({"t": frontier}, budget=100)
    assert len(picks1["t"].contexts) == 1 and math.isclose(loss1, 1.0)


def test_unmeasured_sharing_is_not_used():
    needs, obs = needs_and_obs(agree=True)
    few = Observations()
    for (t, doc), ctx in list(obs.reads.items())[:2]:
        for c, rows in ctx.items():
            few.add(t, doc, c, rows[0])
    d = need_distances(needs, few, FIELDS, {})
    assert math.isinf(d[("q1|t.x", "q2")].ucb)


def test_end_to_end_plan_on_toy(tmp_path):
    spec = toy_spec(tmp_path)
    plan, _obs = build_plan_v3(spec, theta=200_000, caller=fake_caller_factory(responder)(200_000),
                               journal=tmp_path / "j.jsonl")
    cols = plan["columns"]
    # hearing_year agrees under every context: one shared provider serves both queries.
    assert len(cols["c.hearing_year"]) == 1
    # verdict: canonical says "rejected", both queries say "Dismissed": queries share each other's read,
    # the canonical read is never chosen for it.
    assert CANONICAL not in cols["c.verdict"]
    assert plan["budget"]["planned"] <= plan["budget"]["available"]

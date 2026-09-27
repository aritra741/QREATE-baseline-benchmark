from __future__ import annotations

from quwarts.core.adapt import controller as C
from quwarts.core.adapt import drift as D

from tests.test_router_probes import toy_spec


def test_representation_separates_clauses():
    r = D.representation("SELECT verdict, COUNT(*) FROM c WHERE hearing_year > 2003 GROUP BY verdict")
    assert r == frozenset({"verdict@group", "verdict@select", "hearing_year@where"}) or \
        r == frozenset({"verdict@group", "hearing_year@where"}) | ({"verdict@select"} & r)


def test_distance_is_zero_for_equal_workloads_and_grows_with_shift():
    a = ["SELECT verdict FROM c", "SELECT verdict FROM c WHERE hearing_year > 1"]
    b = ["SELECT hearing_year FROM c", "SELECT hearing_year FROM c GROUP BY hearing_year"]
    n = 4
    va = D.vector(D.representation(s) for s in a)
    assert D.distance(va, va, n) == 0
    half = D.vector(D.representation(s) for s in [a[0], b[0]])
    assert 0 < D.distance(va, half, n) < D.distance(va, D.vector(D.representation(s) for s in b), n)


def test_novelty_test_uses_the_build_workloads_own_novelty_rate():
    recurring = ["SELECT verdict FROM c"] * 10 + ["SELECT verdict, COUNT(*) FROM c GROUP BY verdict"] * 10
    one_novel = ["SELECT verdict FROM c"] * 9 + ["SELECT hearing_year FROM c"]
    shifted = ["SELECT hearing_year FROM c WHERE hearing_year > 2000"] * 6 + ["SELECT verdict FROM c"] * 4
    assert D.drift_test(recurring, recurring[:10])["p"] == 1.0
    assert D.drift_test(recurring, shifted)["p"] < 0.05
    # A build workload of one-of-a-kind queries has a high novelty rate: one novel query is no shift.
    diverse = [f"SELECT c{i} FROM c" for i in range(10)] + ["SELECT verdict FROM c"] * 2
    assert D.drift_test(diverse, one_novel)["p"] > 0.05


def test_pushdown_keeps_known_conjuncts_only():
    sql = "SELECT AVG(hearing_year) FROM c WHERE verdict = 'Dismissed' AND hearing_year > 2003"
    assert C.pushdown_conjuncts(sql, "c", {"verdict"}) == "(verdict = 'Dismissed')"
    assert C.pushdown_conjuncts(sql, "c", set()) is None
    assert C.pushdown_conjuncts("SELECT x FROM c WHERE verdict = 'A' OR y = 1", "c", {"verdict"}) is None


class Stub:
    def __init__(self):
        self.calls = []

    def pushdown(self, table, sql, known, single):
        if "verdict" not in known or "WHERE" not in sql:
            return None
        return {"1.txt", "2.txt"} if "'A'" in sql else {"3.txt", "4.txt"} if "'B'" in sql else {"5.txt", "6.txt"}

    def patch(self, table, docs, specs, fields, seen):
        self.calls.append(("patch", table, tuple(docs), tuple(f.name for f in specs)))
        return 0

    def rebuild(self, fields, reads, seen):
        self.calls.append(("rebuild",))
        return 0


def materializer(tmp_path, policy, **kw):
    tmp_path.mkdir(parents=True, exist_ok=True)
    spec = toy_spec(tmp_path)
    docs = {"c": [f"{i}.txt" for i in range(1, 9)]}
    costs = C.Costs({("c", d): 1000 for d in docs["c"]})
    build = {"b1": "SELECT verdict, COUNT(*) FROM c GROUP BY verdict", "b2": "SELECT verdict FROM c"}
    return C.Materializer(spec, build, docs, costs, Stub(), policy, **kw)


QUERIES = [("n1", "SELECT AVG(hearing_year) FROM c WHERE verdict = 'A'"),
           ("n2", "SELECT AVG(hearing_year) FROM c WHERE verdict = 'B'"),
           ("n3", "SELECT AVG(hearing_year) FROM c WHERE verdict = 'C'"),
           ("n1", "SELECT AVG(hearing_year) FROM c WHERE verdict = 'A'")]


def test_patch_reads_only_the_pushed_down_documents_and_reuses_cells(tmp_path):
    m = materializer(tmp_path, "patch")
    actions = [m.step(q, s) for q, s in QUERIES]
    assert [a.action for a in actions] == ["patch", "patch", "patch", "answer"]
    assert m.executor.calls[0] == ("patch", "c", ("1.txt", "2.txt"), ("hearing_year",))
    assert actions[1].benefit == actions[0].patch_tokens + actions[1].patch_tokens


def test_eager_rebuilds_at_the_first_miss(tmp_path):
    m = materializer(tmp_path, "eager")
    assert m.step(*QUERIES[0]).action == "rebuild"
    assert m.step(*QUERIES[1]).action == "answer"  # the rebuilt design has the column for every document


def test_benefit_rule_rebuilds_when_patches_reach_the_rebuild_cost(tmp_path):
    m = materializer(tmp_path, "onlinept")
    steps = [m.step(q, s) for q, s in QUERIES]
    r = steps[0].rebuild_tokens
    for st in steps:
        if st.action == "rebuild":
            assert st.benefit == 0 and steps[st.pos - 1].benefit + st.patch_tokens >= r
            break
    else:
        assert sum(st.patch_tokens for st in steps if st.action == "patch") < r


def test_prediction_sets_the_buy_point(tmp_path, monkeypatch):
    # No drift evidence (the window never fills): the rule buys only once the rent reaches R / lambda.
    m = materializer(tmp_path, "drift", min_window=50, trust=0.5)
    for q, s in QUERIES * 3:
        st = m.step(q, s)
        if st.action == "rebuild":
            assert st.patch_tokens >= st.rebuild_tokens or m.steps[st.pos - 1].benefit + st.patch_tokens >= 2 * st.rebuild_tokens
    # Drift predicted: the rule buys once the rent reaches lambda * R.
    monkeypatch.setattr(D, "drift_test", lambda ref, win, **kw: {"p": 0.0, "delta": 1.0})
    m = materializer(tmp_path / "b", "drift", min_window=1, trust=0.5)
    first = m.step(*QUERIES[0])
    assert first.action == ("rebuild" if first.patch_tokens >= 0.5 * first.rebuild_tokens else "patch")

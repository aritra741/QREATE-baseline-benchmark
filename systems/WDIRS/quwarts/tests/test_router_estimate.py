import random
import sqlite3

import pytest

from quwarts.core.router.estimate import estimate, plan_query, project

QUERIES = [
    "SELECT verdict, COUNT(*) AS n FROM legal GROUP BY verdict",
    "SELECT CASE WHEN case_type IN ('Civil Case', 'Commercial Case') THEN case_type ELSE 'Other' END AS fam, "
    "AVG(legal_basis_num) AS avg_b, SUM(CASE WHEN verdict = 'Dismissed' THEN 1 ELSE 0 END) AS dismissed "
    "FROM legal WHERE hearing_year BETWEEN 2006 AND 2008 GROUP BY fam",
    "SELECT COUNT(*) AS n, AVG(case_number) AS avg_c FROM legal WHERE legal_basis_num >= 2",
    "SELECT judge_name, COUNT(*) AS n FROM legal GROUP BY judge_name HAVING COUNT(*) >= 3",
]


def _table(seed: int, n: int = 60) -> sqlite3.Connection:
    rng = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE legal (doc_id TEXT, verdict TEXT, case_type TEXT, legal_basis_num TEXT, "
                 "case_number TEXT, hearing_year TEXT, judge_name TEXT)")
    for i in range(n):
        conn.execute("INSERT INTO legal VALUES (?,?,?,?,?,?,?)", (
            f"{i}.txt", rng.choice(["Dismissed", "Approved", "Others"]),
            rng.choice(["Civil Case", "Commercial Case", "Administrative Case"]),
            str(rng.randint(0, 6)) if rng.random() > 0.1 else None, str(rng.randint(0, 20)),
            str(rng.choice([2005, 2006, 2007, 2008, 2009])), rng.choice(["Flick", "Tracey", "Moore", "Rares"])))
    return conn


def _sql_answer(conn, sql):
    cur = conn.execute(sql)
    names = [d[0] for d in cur.description]
    return sorted((tuple(str(v) if isinstance(v, str) else v for v in row) for row in cur.fetchall()), key=str), names


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == pytest.approx(b)
    return str(a) == str(b)


def _rows(est, names):
    return sorted((tuple(r[n] for n in names) for r in est), key=str)


@pytest.mark.parametrize("sql", QUERIES)
def test_oracle_equal_to_proxy_reproduces_the_proxy_answer(sql):
    conn = _table(1)
    plan = plan_query(sql)
    assert plan.supported, plan.reason
    proxy = project(conn, plan)
    sample = dict(random.Random(2).sample(sorted(proxy.items()), 20))
    est = estimate(plan, proxy, sample, len(proxy))
    want, names = _sql_answer(conn, sql)
    got = _rows(est, names)
    assert len(got) == len(want)
    for g, w in zip(got, want):
        for a, b in zip(g, w):
            assert _same(a, b), (g, w)


@pytest.mark.parametrize("sql", QUERIES)
def test_full_oracle_sample_gives_the_oracle_answer_with_zero_width(sql):
    proxy_conn, oracle_conn = _table(1), _table(7)  # different values for the same documents
    plan = plan_query(sql)
    proxy, oracle = project(proxy_conn, plan), project(oracle_conn, plan)
    est = estimate(plan, proxy, oracle, len(proxy))
    want, names = _sql_answer(oracle_conn, sql)
    got = _rows(est, names)
    assert len(got) == len(want)
    for g, w in zip(got, want):
        for a, b in zip(g, w):
            assert _same(a, b), (g, w)
    for r in est:
        for lo, hi in r["__ci"].values():
            assert hi - lo == pytest.approx(0.0, abs=1e-9)


def test_min_max_are_proxy_only_and_uncertified():
    plan = plan_query("SELECT case_type, MAX(case_number) AS m, COUNT(*) AS n FROM legal GROUP BY case_type")
    conn = _table(3)
    proxy = project(conn, plan)
    est = estimate(plan, proxy, dict(list(proxy.items())[:10]), len(proxy))
    assert all(r["__certified"]["m"] is False and r["__certified"]["n"] is True for r in est)


def test_count_distinct_is_unsupported():
    assert not plan_query("SELECT COUNT(DISTINCT judge_name) FROM legal").supported

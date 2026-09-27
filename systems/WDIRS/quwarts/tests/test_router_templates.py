from quwarts.core.router.templates import (
    column_set,
    drift_split,
    exposure,
    literal_template,
    literals,
    role_signature,
)

Q1 = ("SELECT CASE WHEN case_type IN ('Civil Case', 'Commercial Case') THEN case_type ELSE 'Other' END AS fam, "
      "COUNT(*) AS n FROM legal WHERE hearing_year BETWEEN 2006 AND 2008 GROUP BY fam")
Q2 = ("SELECT CASE WHEN case_type IN ('Administrative Case') THEN case_type ELSE 'Rest' END AS family, "
      "COUNT(*) AS c FROM legal WHERE hearing_year BETWEEN 2005 AND 2009 GROUP BY family")


def test_literal_template_ignores_constants_and_aliases():
    assert literal_template(Q1) == literal_template(Q2)
    assert "$s" in literal_template(Q1) and "$n" in literal_template(Q1)


def test_group_by_alias_resolves_to_columns():
    roles = role_signature(Q1)
    assert ("case_type", "group") in roles
    assert not any(c == "fam" for c, _ in roles)
    assert ("hearing_year", "filter:between") in roles
    assert column_set(Q1) == {"case_type", "hearing_year"}


def test_literals_are_column_constant_pairs():
    assert ("hearing_year", "2006") in literals(Q1)
    assert ("case_type", "Civil Case") in literals(Q1)
    assert not any(v == "Other" for _, v in literals(Q1))  # CASE output labels are not comparisons


def _rows():
    sqls = [
        "SELECT verdict, COUNT(*) FROM legal WHERE case_type = 'Civil Case' GROUP BY verdict",
        "SELECT verdict, COUNT(*) FROM legal WHERE case_type = 'Commercial Case' GROUP BY verdict",
        "SELECT case_type, AVG(legal_basis_num) FROM legal GROUP BY case_type",
        "SELECT case_type, MAX(legal_basis_num) FROM legal GROUP BY case_type",
        "SELECT hearing_year, COUNT(*) FROM legal WHERE hearing_year >= 2006 GROUP BY hearing_year",
        "SELECT hearing_year, COUNT(*) FROM legal WHERE hearing_year >= 2008 GROUP BY hearing_year",
        "SELECT judge_name, COUNT(*) FROM legal WHERE verdict = 'Dismissed' GROUP BY judge_name",
        "SELECT judge_name, AVG(legal_basis_num) FROM legal GROUP BY judge_name",
        "SELECT verdict, AVG(legal_basis_num) FROM legal WHERE hearing_year BETWEEN 2006 AND 2007 GROUP BY verdict",
        "SELECT case_type, COUNT(*) FROM legal WHERE verdict = 'Approved' GROUP BY case_type",
    ]
    return [{"query_id": f"q{i}", "sql": s} for i, s in enumerate(sqls)]


def test_drift_split_every_held_out_query_drifts_and_columns_stay_covered():
    rows = _rows()
    train, test, hidden = drift_split(rows, seed=7, held_out_fraction=0.3)
    assert test and hidden
    assert {r["query_id"] for r in train}.isdisjoint({r["query_id"] for r in test})
    assert len(train) + len(test) == len(rows)
    train_cols = set().union(*(column_set(r["sql"]) for r in train))
    for r in test:
        assert column_set(r["sql"]) <= train_cols
    assert exposure(train, test)["with_any_drift"] == 1.0


def test_drift_split_is_deterministic():
    a = drift_split(_rows(), seed=7, held_out_fraction=0.3)
    b = drift_split(_rows(), seed=7, held_out_fraction=0.3)
    assert [r["query_id"] for r in a[1]] == [r["query_id"] for r in b[1]] and a[2] == b[2]

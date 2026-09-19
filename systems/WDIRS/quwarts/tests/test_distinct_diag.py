from quwarts.core.distinct_diag import (
    classify_witness_values,
    extract_distinct_measures,
    rewrite_distinct_sidecar,
    same_partition,
)


def test_extracts_all_distinct_measures() -> None:
    sql = (
        "SELECT g, COUNT(DISTINCT a.id) AS n, "
        "COUNT(DISTINCT CASE WHEN flag = 1 THEN a.id END) AS m FROM t a GROUP BY g"
    )
    found = extract_distinct_measures(sql)
    assert [item["alias"] for item in found] == ["n", "m"]
    assert found[0]["identity"] is True
    assert found[1]["identity"] is True


def test_rewrite_replaces_only_identity_inside_distinct() -> None:
    sql = "SELECT COUNT(DISTINCT dr.id) AS n FROM drug dr WHERE dr.id != ''"
    out = rewrite_distinct_sidecar(sql)
    assert "dr.__diag_distinct" in out or '__diag_distinct' in out
    assert "COUNT(DISTINCT" in out.upper().replace(" ", "")
    assert "WHERE dr.id" in out or 'WHERE "dr"."id"' in out or "WHERE dr.id" in out.replace('"', "")


def test_null_missing_is_earliest() -> None:
    assert classify_witness_values(None, "12", identity=True, stable="12", in_qw=True, in_gold=True) == "null_missing"
    assert classify_witness_values("name", None, identity=True, stable="12", in_qw=True, in_gold=True) == "null_extra"
    assert classify_witness_values("name", "12", identity=True, stable="12", in_qw=True, in_gold=True) == "synthetic_key"
    assert classify_witness_values(None, "12", identity=True, stable="12", in_qw=False, in_gold=True) == "support_inherited"


def test_partition_ignores_string_labels() -> None:
    assert same_partition(["a", "a", "b"], ["1", "1", "2"])
    assert not same_partition(["a", "a"], ["1", "2"])
    assert not same_partition([None, "a"], ["1", "1"])

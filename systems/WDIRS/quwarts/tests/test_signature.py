from __future__ import annotations

from quwarts.core.signature import (
    audit_workload,
    enumerate_predicates,
    rewrite_sql,
)


def _q(query_id: str, sql: str) -> dict[str, str]:
    return {"query_id": query_id, "sql": sql}


def test_like_and_empty_compare_are_eligible() -> None:
    report = audit_workload(
        [
            _q(
                "q0",
                "SELECT CASE WHEN LOWER(item.form) LIKE '%tab%' THEN 't' "
                "WHEN item.form != '' THEN 'other' END AS family, COUNT(*) "
                "FROM item WHERE item.form != '' GROUP BY family",
            )
        ]
    )
    assert "item.form" in report.signature_eligible
    assert "item.form" not in report.full_value_required


def test_equijoin_is_full_value() -> None:
    report = audit_workload(
        [
            _q(
                "q0",
                "SELECT COUNT(*) FROM left_t a JOIN right_t b ON a.name = b.name",
            )
        ]
    )
    assert "left_t.name" in report.full_value_required
    assert "right_t.name" in report.full_value_required


def test_count_distinct_and_raw_group_are_full_value() -> None:
    report = audit_workload(
        [
            _q("q0", "SELECT name, COUNT(DISTINCT id) FROM item GROUP BY name"),
        ]
    )
    assert "item.name" in report.full_value_required
    assert "item.id" in report.full_value_required


def test_var_like_is_full_value() -> None:
    report = audit_workload(
        [
            _q(
                "q0",
                "SELECT COUNT(*) FROM left_t a JOIN right_t b "
                "ON '|' || a.names || '|' LIKE '%|' || b.name || '|%'",
            )
        ]
    )
    assert "left_t.names" in report.full_value_required
    assert "right_t.name" in report.full_value_required


def test_predicate_dedup_across_queries() -> None:
    queries = [
        _q("q0", "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%'"),
        _q("q1", "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%' AND form != ''"),
    ]
    report = audit_workload(queries)
    preds = enumerate_predicates(report.occurrences, report.signature_eligible)
    likes = [p for p in preds if p.operator == "LIKE"]
    assert len(likes) == 1
    assert likes[0].raw_occurrences == 2
    assert set(likes[0].query_ids) == {"q0", "q1"}


def test_parse_labels_keeps_null_and_status() -> None:
    from quwarts.core.signature_classify import parse_labels, parse_v2
    from quwarts.core.signature import enumerate_predicates, audit_workload

    queries = [_q("q0", "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%'")]
    report = audit_workload(queries)
    preds = enumerate_predicates(report.occurrences, report.signature_eligible)
    present, labels = parse_labels(
        '{"source_present": false, "labels": [{"i": 1, "sql_truth": "TRUE", "classifier_status": "known"}]}',
        preds,
    )
    assert present is False
    assert labels[preds[0].pred_id].sql_truth == "TRUE"
    v2 = parse_v2(
        '{"concepts": [{"i": 1, "applies": "true", "basis": "inferred_from_entity", "status": "known"}]}',
        preds,
    )
    assert v2[preds[0].pred_id].sql_truth == "TRUE"


def test_like_true_forces_nonempty() -> None:
    from quwarts.core.signature_realize import close_attribute, is_membership, is_presence

    queries = [
        _q(
            "q0",
            "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%' AND form != ''",
        )
    ]
    report = audit_workload(queries)
    preds = enumerate_predicates(report.occurrences, report.signature_eligible)
    like = next(p for p in preds if is_membership(p))
    nonempty = next(p for p in preds if is_presence(p))
    closed, violations = close_attribute({like.pred_id: 1, nonempty.pred_id: None}, preds)
    assert "membership_true_nonempty_not_true" in violations
    assert closed[nonempty.pred_id] == 1
    closed2, _ = close_attribute({like.pred_id: None, nonempty.pred_id: 0}, preds)
    assert closed2[like.pred_id] == 0


def test_rewrite_replaces_like_with_signature() -> None:
    queries = [_q("q0", "SELECT COUNT(*) FROM item WHERE LOWER(form) LIKE '%tab%'")]
    report = audit_workload(queries)
    preds = enumerate_predicates(report.occurrences, report.signature_eligible)
    rewritten = rewrite_sql(queries[0]["sql"], preds)
    assert preds[0].sig_name in rewritten
    assert preds[0].resolved_name in rewritten
    assert "LIKE" in rewritten.upper()
    assert "CASE WHEN" in rewritten.upper()

from pathlib import Path

from quwarts.core.models import AttributeRequirement, Role, Workload
from quwarts.core.query_witness_acq.config import THETA_100, THETA_25, verify_budgets
from quwarts.core.query_witness_acq.programs import compile_programs
from quwarts.core.query_witness_acq.sidecar import (
    probe_witness_additivity,
    program_id_from_sql,
    rewrite_witness_sql,
    write_witness_gate_fixture,
)


def test_budgets_come_from_experiment_config() -> None:
    report = verify_budgets()
    assert report["theta_25"] == 345457
    assert report["theta_100"] == report["docetl_tokens"]
    assert THETA_25 == 345457
    assert THETA_100 == report["docetl_tokens"]
    assert report["theta_100_is_exactly_4x_theta_25"] is (THETA_100 == 345457 * 4)


def test_identical_conditions_dedup() -> None:
    sql_a = "SELECT CASE WHEN auditor LIKE '%KPMG%' THEN 'KPMG' ELSE 'Other' END AS g, COUNT(*) FROM finance WHERE auditor <> '' GROUP BY g"
    sql_b = "SELECT CASE WHEN auditor LIKE '%KPMG%' THEN 'KPMG' ELSE 'Other' END AS g, COUNT(*) FROM finance WHERE auditor <> '' GROUP BY g"
    workload = Workload(
        templates=[],
        requirements={
            "finance.auditor": AttributeRequirement(
                name="finance.auditor",
                entity_type="finance",
                dtype="string",
                roles={Role.PREDICATE, Role.GROUP},
                freq_weight=2.0,
            )
        },
    )
    programs = compile_programs(
        [{"query_id": "q1", "sql": sql_a}, {"query_id": "q2", "sql": sql_b}],
        workload,
    )
    assert len(programs) == 1
    assert programs[0].query_ids == ["q1", "q2"]
    assert program_id_from_sql(sql_a) == programs[0].program_id


def test_rewrite_is_or_exists_and_noops_without_table(tmp_path) -> None:
    sql = "SELECT COUNT(*) FROM finance WHERE auditor <> ''"
    assert "query_witness_additions" not in rewrite_witness_sql(sql, tmp_path / "missing.db")


def test_witness_sidecar_survives_official_sql(tmp_path: Path) -> None:
    db = write_witness_gate_fixture(tmp_path / "witness_gate.db")
    report = probe_witness_additivity(db)
    names = {item["name"]: item for item in report["checks"]}
    assert report["ok"], report["checks"]
    assert names["empty_sidecar_original_count"]["ok"]
    assert names["positive_sidecar_count_plus_one"]["ok"]
    assert names["positive_survives_commit_via_official_sql"]["ok"]
    assert names["removing_sidecar_restores_count"]["ok"]
    assert names["grouped_count_admits_excluded"]["ok"]
    assert names["count_column_plus_one"]["ok"]
    assert names["count_distinct_new_name"]["ok"]
    assert names["table_alias_count_plus_one"]["ok"]
    assert names["join_does_not_invent_edge"]["ok"]
    assert names["null_sentinel_left_join"]["ok"]
    assert names["reuse_same_condition_distinct_programs"]["ok"]
    assert names["reuse_a_only_sees_own_program"]["ok"]
    assert names["reuse_b_unaffected_by_a"]["ok"]
    assert names["reuse_b_own_materialization"]["ok"]

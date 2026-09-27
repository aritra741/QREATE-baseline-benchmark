"""Constants are template parameters: nothing the system builds may be tied to the workload's constants."""

from quwarts.core.router.describe import constrains_domain
from quwarts.core.router.templates import drift_split
from quwarts.core.router.workload_features import AttributeUse, usage_phrase
from quwarts.eval.router_shared_read_run import _label_like

FACTS = {"stored_values": ["Approved", "Dismissed", "Others", "Civil Case", "Commercial Case"]}


def test_enumerating_the_workload_constants_is_a_violation():
    text = "The final decision, which can be 'Approved', 'Dismissed', or 'Others'. Format: string"
    assert constrains_domain(text, FACTS)


def test_catch_all_mapping_is_a_violation():
    text = "The case type. If none of these types are found, it should be marked as 'Other'. Format: string"
    assert any(v.startswith("catch-all") for v in constrains_domain(text, FACTS))


def test_constants_as_examples_are_allowed():
    assert constrains_domain("The final decision, such as 'Approved' or 'Dismissed'. Format: short label", FACTS) == []
    assert constrains_domain("The year of the hearing. Format: number", FACTS) == []


def test_read_prompt_shows_constants_only_as_examples():
    use = AttributeUse(table="legal", name="judge_name", dtype="TEXT", roles=["predicate", "group"],
                       query_ids=["q1"], literals=["Flick", "Greenwood", "Heerey", "Marshall", "Moore"])
    phrase = usage_phrase(use)
    assert "for example" in phrase and "not a complete list" in phrase
    assert "'Heerey'" in phrase and "'Marshall'" not in phrase  # at most three examples


def test_label_form_not_membership():
    assert _label_like("Guilty") and _label_like("Criminal Case")
    assert not _label_like("") and not _label_like("2007")
    assert not _label_like("The court dismissed the appeal. Costs were awarded to the respondent")


def test_drift_split_never_hides_constants_by_default():
    sqls = [
        "SELECT verdict, COUNT(*) FROM legal WHERE case_type = 'Civil Case' GROUP BY verdict",
        "SELECT verdict, COUNT(*) FROM legal WHERE case_type = 'Commercial Case' GROUP BY verdict",
        "SELECT case_type, AVG(legal_basis_num) FROM legal GROUP BY case_type",
        "SELECT case_type, MAX(legal_basis_num) FROM legal GROUP BY case_type",
        "SELECT hearing_year, COUNT(*) FROM legal WHERE hearing_year >= 2006 GROUP BY hearing_year",
        "SELECT judge_name, AVG(legal_basis_num) FROM legal GROUP BY judge_name",
        "SELECT verdict, AVG(legal_basis_num) FROM legal WHERE hearing_year BETWEEN 2006 AND 2007 GROUP BY verdict",
        "SELECT case_type, COUNT(*) FROM legal WHERE verdict = 'Approved' GROUP BY case_type",
    ]
    rows = [{"query_id": f"q{i}", "sql": s} for i, s in enumerate(sqls)]
    _train, _test, hidden = drift_split(rows, seed=3, held_out_fraction=0.3)
    assert hidden and all(item[0] == "role" for item in hidden)

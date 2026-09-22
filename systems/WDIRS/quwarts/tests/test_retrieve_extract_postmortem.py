from quwarts.eval.retrieve_extract_postmortem import classify_route, is_critical, simulated_mode
from quwarts.core.models import Role


def test_whole_document_class_when_both_fits() -> None:
    row = {
        "measurements": {
            "document_tokens": 100,
            "prompt_and_schema_tokens": 40,
            "hard_fit": True,
            "effective_fit": True,
        },
        "retrieval_concentration": {"diffuse": False, "top2_share": 0.9, "unique_sections": 1},
        "remaining_budget": 100000,
        "feasible": ["whole_document", "retrieved_chunks"],
    }
    assert classify_route(row) == "deterministic_whole"
    assert simulated_mode(row) == "whole_document"


def test_unfit_document_is_retrieval() -> None:
    row = {
        "measurements": {
            "document_tokens": 20000,
            "prompt_and_schema_tokens": 40,
            "hard_fit": False,
            "effective_fit": False,
        },
        "retrieval_concentration": {"diffuse": False, "top2_share": 0.8, "unique_sections": 2},
        "remaining_budget": 100000,
        "feasible": ["retrieved_chunks"],
    }
    assert classify_route(row) == "deterministic_retrieval"
    assert simulated_mode(row) == "retrieved_chunks"


def test_diffuse_low_concentration_is_section_map() -> None:
    row = {
        "measurements": {
            "document_tokens": 20000,
            "prompt_and_schema_tokens": 40,
            "hard_fit": False,
            "effective_fit": False,
        },
        "retrieval_concentration": {"diffuse": True, "top2_share": 0.2, "unique_sections": 8},
        "remaining_budget": 100000,
        "feasible": ["retrieved_chunks", "section_map"],
    }
    assert classify_route(row) == "deterministic_section_map"
    assert simulated_mode(row) == "section_map"


def test_predicate_is_critical() -> None:
    assert is_critical({Role.PREDICATE, Role.GROUP}) is True
    assert is_critical({Role.PROJECT}) is False

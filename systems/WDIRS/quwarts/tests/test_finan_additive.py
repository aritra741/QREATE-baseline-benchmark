from quwarts.core.models import AttributeRequirement, Role, Workload
from quwarts.core.retrieve_extract.priority import rank_attributes
from quwarts.core.retrieve_extract.route import decide_coverage_route, measure


def test_coverage_route_is_deterministic() -> None:
    fitted = measure(80, 40, 50)
    mode, reason = decide_coverage_route(fitted, {"diffuse": False, "n_hits": 3, "top2_share": 0.8})
    assert mode == "whole_document"
    long_doc = measure(20_000, 40, 50)
    mode, reason = decide_coverage_route(long_doc, {"diffuse": False, "n_hits": 4, "top2_share": 0.7})
    assert mode == "retrieved_chunks"
    mode, reason = decide_coverage_route(long_doc, {"diffuse": True, "n_hits": 8, "top2_share": 0.2})
    assert mode == "section_map"


def test_rank_uses_gated_formula_not_names() -> None:
    workload = Workload(
        templates=[],
        requirements={
            "rel.alpha": AttributeRequirement(
                name="rel.alpha",
                entity_type="rel",
                dtype="string",
                roles={Role.PREDICATE},
                freq_weight=2.0,
            ),
            "rel.beta": AttributeRequirement(
                name="rel.beta",
                entity_type="rel",
                dtype="numeric",
                roles={Role.PREDICATE, Role.GROUP},
                freq_weight=20.0,
            ),
        },
    )
    ranked = rank_attributes(
        workload,
        gated={"rel.alpha": 1, "rel.beta": 8},
        missing={"rel.alpha": 10, "rel.beta": 10},
        descriptions={"rel.alpha": "", "rel.beta": ""},
    )
    assert ranked[0]["attribute"] == "rel.beta"
    assert ranked[0]["empty_or_zero_support_queries_gated"] == 8
    assert "finance" not in ranked[0]["attribute"]

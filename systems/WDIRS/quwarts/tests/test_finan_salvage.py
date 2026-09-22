from quwarts.core.retrieve_extract.parse import STATUSES
from quwarts.core.retrieve_extract.salvage import salvage_completion, validate_salvaged


def test_unmodified_object_parses() -> None:
    raw = '{"entity_id":"e","attributes":[{"attribute":"rel.a","status":"not_found","raw_value":null,"normalized_value":null,"unit":null,"period":null,"evidence":[]}]}'
    out = salvage_completion(raw, ["rel.a"])
    assert out["parseable_unmodified"] is True
    assert out["by_name"]["rel.a"]["status"] == "not_found"
    assert out["repaired"] is False


def test_fence_and_truncated_recovers_first_object() -> None:
    raw = """here you go
```json
{"entity_id":"e","attributes":[{"attribute":"rel.a","status":"found","raw_value":"12","normalized_value":null,"unit":null,"period":null,"evidence":[{"source_id":"d:c1","exact_span":"revenue 12"}]} , {"attribute":"rel.b","status":"not_found"
"""
    out = salvage_completion(raw, ["rel.a", "rel.b"])
    assert "rel.a" in out["by_name"]
    assert out["by_name"]["rel.a"]["status"] in STATUSES
    assert out["partial"] is True
    assert "truncated JSON" in out["classes"] or "valid partial response" in out["classes"]


def test_duplicate_contradiction_rejected() -> None:
    raw = '{"attributes":[{"attribute":"rel.a","status":"found","raw_value":"1","evidence":[]},{"attribute":"rel.a","status":"found","raw_value":"2","evidence":[]}]}'
    out = salvage_completion(raw, ["rel.a"])
    assert "rel.a" not in out["by_name"]
    assert "duplicate attribute" in out["classes"]


def test_validate_requires_span_in_source() -> None:
    rows = {
        "rel.a": {
            "attribute": "rel.a",
            "status": "found",
            "raw_value": "12",
            "evidence": [{"source_id": "d:c1", "exact_span": "revenue 12"}],
        }
    }
    ok = validate_salvaged(rows, text="revenue 12 this year", digest="h", dtypes={"rel.a": "numeric"}, plumbing_null={"rel.a": True})
    assert ok[0]["sql_eligible"] is True
    bad = validate_salvaged(rows, text="unrelated", digest="h", dtypes={"rel.a": "numeric"}, plumbing_null={"rel.a": True})
    assert bad[0]["sql_eligible"] is False

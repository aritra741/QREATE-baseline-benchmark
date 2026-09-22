from __future__ import annotations

from pathlib import Path

from quwarts.core.retrieve_extract.bundle import pack_bundles
from quwarts.core.retrieve_extract.cache import VerifiedCache, cache_key
from quwarts.core.retrieve_extract.config import FROZEN, MODEL
from quwarts.core.retrieve_extract.index import index_document
from quwarts.core.retrieve_extract.parse import parse_extraction
from quwarts.core.retrieve_extract.route import decide_deterministic, measure


def _manifest(**overrides):
    base = {
        "corpus_id": "A",
        "source_document_hash": "doc",
        "entity_identity": "ent",
        "attribute_bundle": ["x.a"],
        "context_mode": "retrieved_chunks",
        "context_hashes": ["c1"],
        "schema_hash": "s",
        "prompt_hash": "p",
        "model_id": MODEL,
        "configuration_hash": "cfg",
        "operator": "retrieve_extract",
        "tier": "expensive",
    }
    base.update(overrides)
    return base


def test_empty_lookups_are_not_a_perfect_hit_rate(tmp_path: Path) -> None:
    cache = VerifiedCache(tmp_path)
    assert cache.lookups == 0
    assert cache.hit_rate() == "not_applicable"


def test_cache_get_fails_closed_without_verified_fields(tmp_path: Path) -> None:
    cache = VerifiedCache(tmp_path)
    assert cache_key(_manifest(corpus_id="")) is None
    assert cache.get(_manifest(prompt_hash="")) is None
    assert cache.rejected == 1


def test_cache_rejects_cross_corpus_and_cross_prompt(tmp_path: Path) -> None:
    cache = VerifiedCache(tmp_path)
    cache.put(_manifest(), {"raw": "ok"})
    assert cache.get(_manifest(corpus_id="B")) is None
    assert cache.get(_manifest(prompt_hash="other")) is None


def test_whole_document_requires_both_fits() -> None:
    fitted = measure(100, 50, 80)
    assert fitted.hard_fit and fitted.effective_fit
    mode, reason = decide_deterministic(fitted, remaining=10_000, concentration={"diffuse": False})
    assert mode == "whole_document"
    long_doc = measure(20_000, 50, 80)
    assert not long_doc.effective_fit
    mode, _reason = decide_deterministic(long_doc, remaining=10_000, concentration={"diffuse": False})
    assert mode == "retrieved_chunks"
    assert "whole_document" != mode


def test_bundle_size_at_most_three() -> None:
    names = ["a.x", "a.y", "a.z", "a.w"]
    modes = {name: "whole_document" for name in names}
    hits = {name: [] for name in names}
    pri = {name: 1.0 for name in names}
    bundles = pack_bundles(names, modes, hits, pri)
    assert all(1 <= len(bundle.attributes) <= 3 for bundle in bundles)
    assert sum(len(bundle.attributes) for bundle in bundles) == 4


def test_malformed_is_not_not_found() -> None:
    parsed = parse_extraction("not json", ["a.x"], "src", ["s1"], {"a.x": "string"})
    assert parsed["malformed"] is True
    assert parsed["items"]["a.x"]["status"] == "malformed"


def test_unresolved_never_becomes_zero_or_false() -> None:
    raw = """{"entity_id":"e","attributes":[
      {"attribute":"a.x","status":"not_found","raw_value":0,"normalized_value":0,"unit":null,"period":null,"evidence":[]}
    ]}"""
    parsed = parse_extraction(raw, ["a.x"], "nope", [], {"a.x": "numeric"})
    item = parsed["items"]["a.x"]
    assert item["status"] == "not_found"
    assert item["raw_value"] is None
    assert item["normalized_value"] is None


def test_found_requires_exact_span() -> None:
    context = "Revenue was 12 million in 2023."
    raw = """{"entity_id":"e","attributes":[
      {"attribute":"a.x","status":"found","raw_value":"12 million","normalized_value":12000000,
       "unit":null,"period":"2023","evidence":[{"source_id":"s1","exact_span":"12 million"}]}
    ]}"""
    parsed = parse_extraction(raw, ["a.x"], context, ["s1"], {"a.x": "numeric"})
    assert parsed["items"]["a.x"]["grounded"] is True
    bad = raw.replace("12 million", "99 million")
    parsed_bad = parse_extraction(bad, ["a.x"], context, ["s1"], {"a.x": "numeric"})
    assert parsed_bad["items"]["a.x"]["grounded"] is False
    assert parsed_bad["grounding_failures"] == 1


def test_index_preserves_offsets_and_adjacency() -> None:
    text = "INTRODUCTION\nAlpha table\nCol A Col B Col C\n1 2 3\n\nRESULTS\nRevenue was 5.\n"
    index = index_document("d1", text)
    assert index.document_tokens > 0
    assert index.chunks
    assert index.chunks[0].adjacent_next == index.chunks[1].source_id if len(index.chunks) > 1 else True
    assert all(chunk.end > chunk.start for chunk in index.chunks)


def test_effective_input_limit_is_model_level() -> None:
    assert FROZEN["effective_input_limit"] < FROZEN["model_context_limit"]
    assert FROZEN["effective_input_limit"] == 6144

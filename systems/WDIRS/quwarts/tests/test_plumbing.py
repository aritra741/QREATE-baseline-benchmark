from __future__ import annotations

import sqlite3
from pathlib import Path

from quwarts.core.extract import EvidenceStore, evidence_key
from quwarts.core.models import (
    Configuration,
    EvidenceRecord,
    ModuleConfig,
    PopulationPolicy,
    PreprocessPolicy,
    SourceDocument,
)
from quwarts.core.population import apply_population
from quwarts.core.provenance import PROVENANCE_COL, entity_id, identity_collisions, source_document_hash
from quwarts.core.schema import generate_physical_schemas
from quwarts.core.schema_columns import referenced_columns
from quwarts.core.search import config_id
from quwarts.core.workload import analyze_workload


def _record(doc_id: str, attribute: str, value: str | None, key: str) -> EvidenceRecord:
    return EvidenceRecord(
        key=key,
        segment_id=doc_id,
        doc_id=doc_id,
        attribute=attribute,
        surface_value=value,
        parsed_value=value,
        extractor_cfg_hash="cfg",
        quality_tier="cheap",
        stage=1,
    )


def test_empty_lookups_are_not_a_perfect_hit_rate(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "ev")
    store.put(
        _record("a.txt", "finance.revenue", "1", "legacy-key"),
    )
    assert store.lookups == 0
    assert store.cache_hit_rate() != 1.0
    assert store.cache_hit_rate() == 0.0


def test_cache_get_fails_closed_without_verified_fields() -> None:
    store = EvidenceStore()
    assert (
        evidence_key("seg", "finance.revenue", "cfg", "cheap") is None
    )
    assert store.get("seg", "finance.revenue", "cfg", "cheap") is None
    assert store.lookups == 1
    assert store.hits == 0


def test_cache_rejects_cross_corpus_and_cross_prompt() -> None:
    store = EvidenceStore()
    fields = dict(
        corpus_id="Finan",
        source_document_hash="abc",
        entity_identity="ent",
        attribute="finance.revenue",
        schema_hash="sch",
        prompt_hash="p1",
        model_id="qwen",
        extractor_cfg_hash="cfg",
        quality_tier="cheap",
    )
    key = evidence_key(**fields)
    assert key is not None
    store.put(_record("1.txt", "finance.revenue", "2", key))
    hit = store.get(None, **fields)
    assert hit is not None
    miss_corpus = dict(fields)
    miss_corpus["corpus_id"] = "Legal"
    assert store.get(None, **miss_corpus) is None
    miss_prompt = dict(fields)
    miss_prompt["prompt_hash"] = "p2"
    assert store.get(None, **miss_prompt) is None


def test_all_null_entities_are_retained() -> None:
    logical, workload = analyze_workload(
        ["SELECT auditor, revenue FROM finance WHERE revenue > 0"]
    )
    schema = generate_physical_schemas(logical)[0]
    pop = PopulationPolicy()
    pop.er["finance.auditor"] = ModuleConfig(strategy="merge", params={})
    config = Configuration(
        id=config_id(schema, pop, PreprocessPolicy(mode="whole_document"), "c0"),
        schema=schema,
        pop=pop,
        pre=PreprocessPolicy(mode="whole_document"),
        cluster_id="c0",
    )
    docs = [
        SourceDocument(doc_id="1.txt", text="alpha"),
        SourceDocument(doc_id="2.txt", text="beta"),
    ]
    records = [
        _record("1.txt", "finance.auditor", None, "k1"),
        _record("1.txt", "finance.revenue", None, "k2"),
    ]
    rows = apply_population(records, config, workload, documents=docs, corpus_id="Finan")
    assert len(rows) == 2
    assert all(row.get(PROVENANCE_COL) for row in rows)
    assert identity_collisions() == []
    pks = [item for keys in schema.primary_keys.values() for item in keys]
    assert "finance.auditor" not in pks


def test_select_aliases_stay_off_the_physical_schema() -> None:
    names = {
        item.column
        for item in referenced_columns(
            {"q": "SELECT CASE WHEN revenue > 0 THEN 'pos' END AS profit_status, net_assets FROM finance"}
        )
    }
    assert "revenue" in names
    assert "net_assets" in names
    assert "profit_status" not in names


def test_provenance_is_corpus_and_document_scoped() -> None:
    digest = source_document_hash("1.txt", "body")
    left = entity_id("Finan", digest, 0)
    right = entity_id("Legal", digest, 0)
    assert left != right

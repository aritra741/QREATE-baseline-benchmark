from __future__ import annotations

from pathlib import Path

from quwarts.core.extract import EvidenceStore, StagedExtractor, allocate_tiers
from quwarts.core.ledger import TokenLedger
from quwarts.core.materialize import file_sha256, materialize
from quwarts.core.models import Configuration, PreprocessPolicy
from quwarts.core.pipeline import load_documents, synthesize
from quwarts.core.population import apply_population, policy_from_demands, tokens_spent_during_population
from quwarts.core.schema import generate_physical_schemas
from quwarts.core.search import config_id
from quwarts.core.workload import analyze_workload

from conftest import CORPUS


def test_evidence_reuse_and_population_is_free(tmp_path: Path) -> None:
    documents = load_documents(CORPUS)
    logical, workload = analyze_workload(
        ["SELECT player.name FROM player WHERE player.position = 'Guard'"]
    )
    store = EvidenceStore(tmp_path / "evidence")
    ledger = TokenLedger(theta=100000, seed=0)
    extractor = StagedExtractor(store=store, ledger=ledger, seed=0)
    policy = PreprocessPolicy(mode="whole_document")
    tiers = allocate_tiers(workload)
    extractor.extract(documents, workload, policy, tiers)
    spent_after_first = ledger.spent
    lookups_after_first = store.lookups
    extractor.extract(documents, workload, policy, tiers)
    assert store.hits > 0
    assert ledger.spent == spent_after_first
    assert store.lookups > lookups_after_first

    schema = generate_physical_schemas(logical)[0]
    pop = policy_from_demands({}, workload)
    config = Configuration(
        id=config_id(schema, pop, policy, "c0"),
        schema=schema,
        pop=pop,
        pre=policy,
        cluster_id="c0",
    )
    before = ledger.spent
    rows = apply_population(list(store.records.values()), config, workload)
    assert rows
    assert tokens_spent_during_population() == 0
    assert ledger.spent == before
    db = materialize(config, list(store.records.values()), workload, documents, tmp_path / "db", before)
    assert Path(db.sqlite_path).exists()
    assert db.sha256 == file_sha256(Path(db.sqlite_path))


def test_deterministic_replay(tmp_path: Path) -> None:
    documents = load_documents(CORPUS)
    statements = ["SELECT player.name FROM player WHERE player.position = 'Guard'"]
    a = synthesize(documents, statements, theta=5000, seed=7, artifact_root=tmp_path / "a")
    b = synthesize(documents, statements, theta=5000, seed=7, artifact_root=tmp_path / "b")
    assert [db.sha256 for db in a.databases] == [db.sha256 for db in b.databases]
    assert a.logical_schema.id == b.logical_schema.id

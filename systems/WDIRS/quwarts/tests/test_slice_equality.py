from __future__ import annotations

import sqlite3
from pathlib import Path

from quwarts.core.extract import EvidenceStore, StagedExtractor, allocate_tiers
from quwarts.core.ledger import TokenLedger
from quwarts.core.materialize import materialize
from quwarts.core.models import Configuration, PreprocessPolicy, TemplateShape
from quwarts.core.pipeline import load_documents
from quwarts.core.population import policy_from_demands
from quwarts.core.schema import generate_physical_schemas
from quwarts.core.search import config_id
from quwarts.core.workload import analyze_workload, classify_shape, parse_sql

from conftest import CORPUS

SHAPES = {
    TemplateShape.FILTERED_PROJECTION: "SELECT player.name FROM player WHERE player.position = 'Guard'",
    TemplateShape.FILTERED_AGGREGATE: "SELECT SUM(player.salary) FROM player WHERE player.salary > 1000000",
    TemplateShape.CROSS_ATTRIBUTE_FILTER: "SELECT SUM(player.salary) FROM player WHERE player.position = 'Guard'",
    TemplateShape.UNFILTERED_AGGREGATE: "SELECT AVG(player.salary) FROM player",
    TemplateShape.BASE_CARDINALITY: "SELECT COUNT(*) FROM player",
    TemplateShape.ANTI_JOIN: (
        "SELECT player.name FROM player WHERE player.team_id NOT IN "
        "(SELECT team.id FROM team WHERE team.city = 'Boston')"
    ),
}


def _materialize(tmp_path: Path, sql: str, full_slice: bool) -> list[tuple]:
    documents = load_documents(CORPUS)
    logical, workload = analyze_workload([sql])
    if full_slice:
        for req in workload.requirements.values():
            from quwarts.core.models import SliceSpec

            req.slice = SliceSpec(kind="full")
            for template in workload.templates:
                template.slice_safe = False
    store = EvidenceStore(tmp_path / ("full" if full_slice else "staged"))
    ledger = TokenLedger(theta=100000, seed=0)
    extractor = StagedExtractor(store=store, ledger=ledger, seed=0)
    policy = PreprocessPolicy(mode="whole_document")
    extractor.extract(documents, workload, policy, allocate_tiers(workload))
    schema = generate_physical_schemas(logical)[0]
    pop = policy_from_demands({}, workload)
    config = Configuration(
        id=config_id(schema, pop, policy, "c0"),
        schema=schema,
        pop=pop,
        pre=policy,
        cluster_id="c0",
    )
    db = materialize(config, list(store.records.values()), workload, documents, tmp_path / "db", ledger.spent)
    conn = sqlite3.connect(db.sqlite_path)
    try:
        # Compare the populated fact table, not the rewrite, so shape equality
        # is about extraction completeness.
        rows = list(conn.execute("SELECT * FROM fact ORDER BY 1"))
    finally:
        conn.close()
    return rows


def test_every_shape_classifies() -> None:
    for shape, sql in SHAPES.items():
        got, _ = classify_shape(parse_sql(sql))
        assert got == shape


def test_staged_equals_full_on_slice_safe_shapes(tmp_path: Path) -> None:
    for shape, sql in SHAPES.items():
        _, safe = classify_shape(parse_sql(sql))
        if not safe:
            continue
        staged = _materialize(tmp_path / shape.value / "s", sql, full_slice=False)
        full = _materialize(tmp_path / shape.value / "f", sql, full_slice=True)
        assert staged == full, shape

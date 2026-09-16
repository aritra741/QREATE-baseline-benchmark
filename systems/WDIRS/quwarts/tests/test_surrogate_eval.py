from __future__ import annotations

from pathlib import Path

from quwarts.core.models import (
    Configuration,
    CoverageSet,
    MaterializedDB,
    PhysicalSchema,
    PopulationPolicy,
    PreprocessPolicy,
    Relation,
    SliceSpec,
    SourceDocument,
    SurrogateReport,
)
from quwarts.core.surrogate import U_hat
from quwarts.core.workload import analyze_workload
from quwarts.eval import cell_score, error, f1


def _empty_schema() -> PhysicalSchema:
    return PhysicalSchema(
        id="s",
        pattern="denormalized",
        relations=[Relation(name="fact", attributes=["name", "salary"])],
        primary_keys={"fact": ["name"]},
        foreign_keys=[],
        declared_fds=[],
        declared_dcs=[],
        covered_attributes={"player.name", "player.salary", "name", "salary"},
    )


def test_record_dropping_config_does_not_win(tmp_path: Path) -> None:
    _, workload = analyze_workload(["SELECT player.name FROM player"])
    for req in workload.requirements.values():
        req.amp = 4.0
    schema = _empty_schema()
    config = Configuration(
        id="full",
        schema=schema,
        pop=PopulationPolicy(),
        pre=PreprocessPolicy(mode="whole_document"),
        cluster_id="c0",
    )
    dropping = Configuration(
        id="drop",
        schema=schema,
        pop=PopulationPolicy(),
        pre=PreprocessPolicy(mode="whole_document"),
        cluster_id="c0",
    )
    docs = [SourceDocument(doc_id=f"d{i}", text=f"name: p{i} salary: {i}") for i in range(8)]

    def write(name: str, n: int) -> Path:
        path = tmp_path / f"{name}.db"
        import sqlite3

        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE fact (name TEXT, salary TEXT)")
        for i in range(n):
            conn.execute("INSERT INTO fact VALUES (?, ?)", (f"p{i}", str(i)))
        conn.commit()
        conn.close()
        return path

    full_path = write("full", 8)
    drop_path = write("drop", 2)
    coverage = CoverageSet(
        attribute_ranges={"player.name": SliceSpec(kind="full")},
        attributes_present={"player.name", "player.salary"},
        grain={"player": "mention"},
        forms={"player.name": {"surface"}},
        corpus_fingerprint="x",
    )
    full_db = MaterializedDB(
        config_id="full", sqlite_path=str(full_path), sha256="a",
        row_counts={"fact": 8}, tokens_spent=0, coverage=coverage,
        surrogate=SurrogateReport(U_hat=0, signals={}),
    )
    drop_db = MaterializedDB(
        config_id="drop", sqlite_path=str(drop_path), sha256="b",
        row_counts={"fact": 2}, tokens_spent=0, coverage=coverage,
        surrogate=SurrogateReport(U_hat=0, signals={}),
    )
    full_score = U_hat(full_db, config, docs, workload).U_hat
    drop_score = U_hat(drop_db, dropping, docs, workload).U_hat
    assert drop_score <= full_score


def test_eval_protocol() -> None:
    gold = [{"name": "Alice", "salary": "10"}, {"name": "Bob", "salary": "20"}]
    pred = [{"name": "Alice", "salary": "10"}, {"name": "Bob", "salary": "21"}]
    assert cell_score("Alice", "Alice") == (1.0, 1.0)
    value = error(gold, pred, ["name"], ["name", "salary"], {"salary": "numeric"})
    assert 0.0 < value < 1.0
    assert f1(1, 1) == 1.0

from __future__ import annotations

import json
import re
from pathlib import Path

from quwarts.core.router.probes import AttributeProbe, fake_caller_factory, parse_fields, run_probe, same_value
from quwarts.core.router.registry import CorpusSpec, TableSpec
from quwarts.core.router.text import find_span, prepare_document
from quwarts.core.router.workload_features import workload_features


def toy_spec(tmp_path: Path) -> CorpusSpec:
    docs = tmp_path / "docs"
    docs.mkdir()
    for index in range(1, 9):
        (docs / f"{index}.txt").write_text(
            f"Case {index}\nHearing year: {2000 + index}\nThe court considered the appeal and it was rejected.\n"
        )
    attrs = tmp_path / "attrs.json"
    attrs.write_text(json.dumps({"case": {
        "hearing_year": {"value_type": "int", "description": "year of the hearing"},
        "verdict": {"value_type": "str", "description": "choose one from [Approved, Dismissed]", "is_fixed": True},
    }}))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"query_id": "q1", "sql": "SELECT verdict, AVG(hearing_year) FROM c GROUP BY verdict"},
        {"query_id": "q2", "sql": "SELECT COUNT(*) FROM c WHERE verdict = 'Dismissed' AND hearing_year > 2003"},
    ]))
    return CorpusSpec(name="toy", tables=(TableSpec("c", "case", docs),), attributes_json=(attrs,), manifest=manifest)


def responder(prompt: str, metadata: dict) -> str:
    year = re.search(r"Hearing year: (\d{4})", prompt).group(1)
    # Interpretive label: canonical asks give one reading, query-conditioned asks another.
    verdict = "Dismissed" if metadata.get("kind") == "conditioned" else "rejected"
    return json.dumps({"fields": {"hearing_year": int(year), "verdict": verdict}})


def test_probe_separates_extractive_from_query_sensitive(tmp_path):
    spec = toy_spec(tmp_path)
    wf = workload_features(spec)
    uses = list(wf["attributes"].values())
    tokens = {"c": {f"{i}.txt": 30 for i in range(1, 9)}}
    caller = fake_caller_factory(responder)(200_000)
    out = run_probe(spec, uses, spec.queries(), tokens, caller, journal=tmp_path / "journal.jsonl")
    metrics = out["tables"]["c"]["metrics"]
    year, verdict = metrics["c.hearing_year"], metrics["c.verdict"]
    assert year["kappa"] == 1.0 and year["g"] == 1.0 and year["delta"] == 0.0
    assert year["r"] == 1.0  # every year follows the same "hearing year:" cue
    assert verdict["delta"] == 1.0  # canonical and query readings never agree
    assert verdict["delta_cross"] == 0.0  # but the two query readings agree with each other
    assert verdict["g"] < 1.0  # "Dismissed" is not a span; "rejected" is
    rows = (tmp_path / "journal.jsonl").read_text().splitlines()
    assert rows and all("response" in json.loads(row) for row in rows)
    assert caller.ledger.spent > 0


def test_probe_respects_budget(tmp_path):
    spec = toy_spec(tmp_path)
    uses = list(workload_features(spec)["attributes"].values())
    tokens = {"c": {f"{i}.txt": 30 for i in range(1, 9)}}
    caller = fake_caller_factory(responder)(500)
    out = run_probe(spec, uses, spec.queries(), tokens, caller, budget=500)
    assert caller.ledger.spent <= 500
    assert out["tables"]["c"]["plan"]["affordable"] is False


def test_noise_is_subtracted_from_query_sensitivity():
    probe = AttributeProbe("t.a")
    docs = {f"d{i}": "text" for i in range(4)}
    # Two identical requests disagree on half the documents: kappa = 0.5.
    probe.canonical = {"d0": ("x", "x"), "d1": ("x", "y"), "d2": ("x", "x"), "d3": ("x", "y")}
    probe.conditioned = [("d0", "q", "x"), ("d1", "q", "y"), ("d2", "q", "x"), ("d3", "q", "y")]
    metrics = probe.metrics(docs)
    assert metrics["kappa"] == 0.5
    assert metrics["delta_raw"] == 0.5 and metrics["delta"] == 0.0


def test_helpers():
    assert parse_fields('```json\n{"fields": {"a": 1}}\n```') == {"a": 1}
    assert same_value("1,000", 1000) and not same_value("EY", "Ernst & Young")
    doc = prepare_document("Filed in 2008. Count: 0 items")
    assert find_span(0, doc) > find_span(2008, doc) >= 0  # "0" is not matched inside "2008"

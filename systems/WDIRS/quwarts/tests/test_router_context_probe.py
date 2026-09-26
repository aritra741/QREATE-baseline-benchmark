from __future__ import annotations

import json
import re

from quwarts.core.router.context_probe import contexts_by_table, field_specs, run_context_probe
from quwarts.core.router.needs import CANONICAL, workload_needs
from quwarts.core.router.probes import fake_caller_factory

from tests.test_router_probes import toy_spec


def responder(prompt: str, metadata: dict) -> str:
    year = re.search(r"Hearing year: (\d{4})", prompt).group(1)
    verdict = "Dismissed" if metadata.get("context") != CANONICAL else "rejected"
    return json.dumps({"fields": {"hearing_year": int(year), "verdict": verdict}})


def test_contexts_and_fields(tmp_path):
    spec = toy_spec(tmp_path)
    needs = workload_needs(spec)
    ctx = contexts_by_table(needs)["c"]
    assert set(ctx) == {"q1", "q2", CANONICAL}
    assert {n.attribute for n in ctx[CANONICAL]} == {"hearing_year", "verdict"}
    fields = field_specs(spec, needs, set())
    assert fields["c.hearing_year"].value_type == "int"


def test_probe_builds_pairs_and_noise_within_budget(tmp_path):
    spec = toy_spec(tmp_path)
    needs = workload_needs(spec)
    tokens = {"c": {f"{i}.txt": 30 for i in range(1, 9)}}
    caller = fake_caller_factory(responder)(20_000)
    out = run_context_probe(spec, needs, spec.queries(), tokens, field_specs(spec, needs, set()), caller,
                            budget=20_000, journal=tmp_path / "j.jsonl")
    assert out["spent"] <= 20_000
    pairs = out["pair_counts"]
    # Every need got paired against the canonical read and against the other query.
    assert any(k.endswith(f"<-{CANONICAL}") for k in pairs)
    assert any("q1|" in k and k.endswith("<-q2") for k in pairs)
    reads = out["observations"]
    repeats = sum(1 for ctx in reads.values() for rows in ctx.values() if len(rows) > 1)
    assert repeats >= 1  # noise floor measured
    assert len((tmp_path / "j.jsonl").read_text().splitlines()) == sum(len(r) for c in reads.values() for r in c.values())


def test_schema_contract_parsing_and_conformance():
    from quwarts.core.router.context_probe import FieldSpec, conform, declared_choices

    choices, multi = declared_choices("whether X, choose one from ['Yes', 'No'].")
    assert choices == ("Yes", "No") and not multi
    choices, multi = declared_choices("domains, choose one or more from ['General', 'Medical', 'Other']")
    assert multi and "Medical" in choices
    yn = FieldSpec("r", "str", "", nullable=False, choices=("Yes", "No"))
    assert conform("yes", yn) == "Yes" and conform("Maybe", yn) is None and conform(None, yn) is None
    assert "Answer No unless the document indicates Yes" in yn.line() and "Never null" in yn.line()
    multi_f = FieldSpec("m", "str", "", choices=("Text", "Image", "Audio"), multi_choice=True)
    assert conform("text || Video || Image", multi_f) == "Text || Image"


def test_description_can_declare_an_empty_case(tmp_path):
    import json

    from quwarts.core.router.registry import CorpusSpec, TableSpec

    attrs = tmp_path / "a.json"
    attrs.write_text(json.dumps({"p": {"fw": {"value_type": "str", "is_nullable": False,
        "description": "framework, choose one from ['CoT', 'Other'], if the system does not use agent, leave it empty."}}}))
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps([{"query_id": "q", "sql": "SELECT fw, COUNT(*) FROM t GROUP BY fw"}]))
    spec = CorpusSpec("x", (TableSpec("t", "p", tmp_path),), (attrs,), manifest)
    fields = field_specs(spec, workload_needs(spec), set())
    assert fields["t.fw"].nullable and fields["t.fw"].choices == ("CoT", "Other")


def test_declared_absence_values():
    from quwarts.core.router.context_probe import FieldSpec, absence_value, complete

    yn = FieldSpec("r", "str", "whether it uses X", nullable=False, choices=("Yes", "No"))
    count = FieldSpec("n", "int", "Number of awards (use 0 if none)", nullable=False)
    name = FieldSpec("a", "str", "name of the audit firm", nullable=False)
    optional = FieldSpec("f", "str", "framework", nullable=True, choices=("Yes", "No"))
    assert complete(None, yn) == "No" and complete("yes", yn) == "Yes"
    assert complete(None, count) == 0 and complete(3, count) == 3
    assert absence_value(name) is None and absence_value(optional) is None


def test_bare_choice_lists_and_declared_zero():
    from quwarts.core.router.context_probe import FieldSpec, absence_value, declared_choices

    assert declared_choices("type, choose one from [Criminal Case, Civil Case]; (e.g., Civil Case)")[0] == ("Criminal Case", "Civil Case")
    assert declared_choices("continent, select one from [Africa, Asia, Europe]")[0] == ("Africa", "Asia", "Europe")
    assert declared_choices("decision, choose one from: [Guilty, Not Guilty, Others]")[0] == ("Guilty", "Not Guilty", "Others")
    assert absence_value(FieldSpec("first_judge", "str", "whether first (1 if yes, 0 if none)", nullable=False)) == 0

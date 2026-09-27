"""System reads must see only documents, the SQL workload and theta (RULES.md)."""

from __future__ import annotations

import json

import pytest

from quwarts.core.router.context_probe import field_specs, render_prompt
from quwarts.core.router.needs import workload_needs
from quwarts.core.router.registry import REGISTRY
from quwarts.core.router.workload_features import usage_phrase, workload_features
from dataclasses import replace


def description_fragments(spec) -> list[str]:
    frags = []
    for path in spec.attributes_json:
        for attrs in json.loads(path.read_text()).values():
            for record in attrs.values():
                text = str(record.get("description") or "")
                # every 30-character window of a description is a distinctive fragment
                frags.extend(text[i:i + 30] for i in range(0, max(1, len(text) - 30), 15) if len(text) >= 30)
    return frags


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_read_prompts_contain_no_attribute_file_text(name):
    spec = REGISTRY[name]
    queries = spec.queries()
    needs = workload_needs(spec, queries)
    wf = workload_features(spec, queries)
    numeric = {q for q, u in wf["attributes"].items() if u.numeric}
    fields = field_specs(spec, needs, numeric)
    fields = {q: replace(f, usage=usage_phrase(wf["attributes"][q])) for q, f in fields.items() if q in wf["attributes"]}
    prompt = render_prompt("DOC", list(fields.values()), None)
    # Text the SQL workload itself supplies (its literals, via usage phrases) is allowed.
    allowed = " ".join(queries.values()) + " " + " ".join(f.usage for f in fields.values())
    for frag in description_fragments(spec):
        assert not (frag in prompt and frag not in allowed), f"{name}: attribute-file text leaked: {frag!r}"
    for f in fields.values():
        assert f.description == "" and f.choices == () and f.nullable


def test_descriptions_are_not_a_system_input():
    spec = REGISTRY["legal"]
    with pytest.raises(PermissionError):
        spec.descriptions()
    with pytest.raises(PermissionError):
        spec.benchmark_attribute_descriptions(purpose="reads")
    assert spec.benchmark_attribute_descriptions(purpose="scoring")
    assert spec.benchmark_attribute_descriptions(purpose="protocol")  # the benchmark's published input


def test_protocol_fields_carry_the_benchmark_schema():
    from quwarts.core.router.context_probe import protocol_field_specs

    spec = REGISTRY["legal"]
    queries = spec.queries()
    fields = protocol_field_specs(spec, workload_needs(spec, queries))
    assert all(f.description for f in fields.values())
    assert any(f.choices for f in fields.values())  # declared "choose from [...]" label sets

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

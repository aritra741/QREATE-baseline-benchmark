from __future__ import annotations

import json
import re

from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router import chunked
from quwarts.core.router.context_probe import V3, FieldSpec
from quwarts.core.router.executor import Read, load_values, run_reads
from quwarts.core.router.probes import fake_caller_factory

from tests.test_router_probes import toy_spec


def test_split_chunks_cover_text_within_budget():
    text = "".join(f"Line {i}: revenue was {i * 7} thousand dollars in the period.\n" for i in range(400))
    chunks = chunked.split_chunks(text, 300)
    assert "".join(chunks) == text and len(chunks) > 5
    assert all(count_tokens(c) <= 302 for c in chunks)
    assert all(c.endswith("\n") for c in chunks)  # cut at line breaks
    assert chunked.split_chunks("short text", 300) == ["short text"]


def test_reduce_votes_ignore_absence_and_tie_to_earliest():
    yes_no = FieldSpec("flag", "str", "", nullable=False, choices=("Yes", "No"))
    assert chunked.reduce_chunks([{"flag": "No"}, {"flag": "Yes"}, {"flag": "No"}], yes_no) == ("Yes", [1])
    assert chunked.reduce_chunks([{"flag": "No"}, {"flag": None}], yes_no) == (None, [])  # absence at commit
    num = FieldSpec("revenue", "float", "")
    answers = [{"revenue": "$2 million"}, {"revenue": 5}, {"revenue": 2000000}, {"revenue": None}]
    assert chunked.reduce_chunks(answers, num) == (2_000_000, [0, 2])
    assert chunked.reduce_chunks([{"revenue": 5}, {"revenue": 7}], num) == (5, [0])  # tie: earliest
    many = FieldSpec("segments", "multi_str", "")
    value, support = chunked.reduce_chunks([{"segments": "Retail || Energy"}, {"segments": ["energy", "Mining"]}], many)
    assert value == "Retail || Energy || Mining" and support == [0, 1]


def test_parse_carry():
    assert chunked.parse_carry('{"fields": {}, "context_for_next_part": "Acme Corp, FY2021, USD"}', "") == "Acme Corp, FY2021, USD"
    assert chunked.parse_carry('garbage', "old") == "old"
    assert chunked.parse_carry('{"fields": {"a": 1}, "context_for_next_part": "Acme', "old") == "old"
    assert chunked.parse_carry('{"fields": {"a": 1 "context_for_next_part": "Acme \\"X\\"" }', "old") == 'Acme "X"'


def test_chain_carries_context_and_resumes(tmp_path, monkeypatch):
    spec = toy_spec(tmp_path)
    long = "Hearing year: 2011\n" + "".join(f"The court then considered item {i} of the record.\n" for i in range(300))
    long += "The appeal was Dismissed.\n"
    (tmp_path / "docs" / "9.txt").write_text(long)
    monkeypatch.setitem(V3, "window_tokens", 1300)
    prompts = []

    def responder(prompt, metadata):
        prompts.append(prompt)
        part = int(re.search(r"part (\d+) of", prompt).group(1)) if "part " in prompt else 0
        year = re.search(r"Hearing year: (\d{4})", prompt)
        verdict = "Dismissed" if "was Dismissed" in prompt else None
        fields = {"hearing_year": int(year.group(1)) if year else None, "verdict": verdict}
        return json.dumps({"fields": fields, "context_for_next_part": f"case 9, notes after part {part}"})

    fields = {"c.verdict": FieldSpec("verdict", "str", "", choices=("Approved", "Dismissed")),
              "c.hearing_year": FieldSpec("hearing_year", "int", "")}
    reads = [Read("c", "__workload__", ("hearing_year", "verdict"))]
    journal = tmp_path / "reads.jsonl"
    caller = fake_caller_factory(responder)(10**9)
    stats = run_reads(spec, reads, {}, fields, caller, journal, workers=2, long_documents="chain")
    assert stats["chained_documents"] == 1 and stats["chunks"] >= 3
    chunk_prompts = [p for p in prompts if "PART " in p]
    assert "None: this is the first part." in chunk_prompts[0]
    rows = [json.loads(l) for l in journal.read_text().splitlines() if "chunk" in json.loads(l)]
    assert rows[1]["carry_in"] == "case 9, notes after part 1"
    assert all(r["carry_in"] == f"case 9, notes after part {r['chunk']}" for r in rows[1:])
    prov = {}
    values = load_values(journal, fields, prov)[("c", "__workload__")]
    assert values["9.txt"] == {"hearing_year": 2011, "verdict": "Dismissed"}
    assert prov[("c", "__workload__", "9.txt", "verdict")] == [len(rows) - 1]
    assert values["1.txt"]["hearing_year"] == 2001  # short documents: one read, as before
    before = len(prompts)
    stats = run_reads(spec, reads, {}, fields, caller, journal, workers=2, long_documents="chain")
    assert len(prompts) == before and stats["chunk_calls"] == 0  # resumed from the journal


def test_split_chunks_are_even():
    text = "".join(f"Line {i}: revenue was {i * 7} thousand dollars in the period.\n" for i in range(400))
    sizes = [count_tokens(c) for c in chunked.split_chunks(text, 1000)]
    assert max(sizes) <= 1002 and min(sizes) > 0.8 * max(sizes)


def test_compact_and_rejected_chunk_is_retried_compacted(tmp_path, monkeypatch):
    assert chunked.compact("| a      | b |\n|--------|---|\n") == "| a | b |\n|---|---|\n"
    spec = toy_spec(tmp_path)
    long = "Hearing year: 2011\n" + "".join(f"| item {i}" + " " * 200 + "|\n" for i in range(300))
    (tmp_path / "docs" / "9.txt").write_text(long)
    monkeypatch.setitem(V3, "window_tokens", 1300)
    calls = []

    def responder(prompt, metadata):
        if "PART " in prompt and "     " in prompt:
            raise RuntimeError("This endpoint's maximum context length is 32768 tokens.")
        calls.append(prompt)
        return json.dumps({"fields": {"hearing_year": 2011}, "context_for_next_part": "case 9"})

    fields = {"c.verdict": FieldSpec("verdict", "str", ""), "c.hearing_year": FieldSpec("hearing_year", "int", "")}
    reads = [Read("c", "__workload__", ("hearing_year", "verdict"))]
    journal = tmp_path / "reads.jsonl"
    caller = fake_caller_factory(responder)(10**9)
    stats = run_reads(spec, reads, {}, fields, caller, journal, workers=1, long_documents="chain")
    rows = [json.loads(l) for l in journal.read_text().splitlines() if "chunk" in json.loads(l)]
    assert rows and all(r["compacted"] for r in rows) and len(rows) == stats["chunks"]
    n = len(calls)
    run_reads(spec, reads, {}, fields, caller, journal, workers=1, long_documents="chain")
    assert len(calls) == n  # replay finds the compacted prompts

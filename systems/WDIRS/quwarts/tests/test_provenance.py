from __future__ import annotations

import json
import re
import shutil
import sqlite3

import pytest

from quwarts.core.lineage import maintain as M
from quwarts.core.lineage import store as S
from quwarts.core.router.context_probe import V3, FieldSpec
from quwarts.core.router.executor import Read, load_values, run_reads
from quwarts.core.router.probes import fake_caller_factory

from quwarts.eval.router_provenance import build
from tests.test_router_probes import toy_spec

FIELDS = {"c.verdict": FieldSpec("verdict", "str", "", choices=("Approved", "Dismissed")),
          "c.hearing_year": FieldSpec("hearing_year", "int", "")}
READS = [Read("c", "__workload__", ("hearing_year", "verdict"))]
LONG = "Hearing year: 2011\n" + "".join(f"The court then considered item {i} of the record.\n" for i in range(300)) + \
    "The appeal was Dismissed.\n"


def responder(prompt, metadata):
    year = re.search(r"Hearing year: (\d{4})", prompt.split("FIELDS:")[0].split("DOCUMENT CONTEXT")[-1] if "PART " in prompt else prompt)
    verdict = "Dismissed" if "was Dismissed" in prompt else None
    fields = {"hearing_year": int(year.group(1)) if year else None, "verdict": verdict}
    if "PART " not in prompt:
        return json.dumps({"fields": fields})
    part = prompt.split("PART ", 1)[1].split("FIELDS:")[0]
    filler = "continues" if len(part) % 2 else "goes on"  # a note whose wording, not facts, depends on the text
    return json.dumps({"fields": fields, "context_for_next_part": f"Case 9 {filler}"})


@pytest.fixture
def run(tmp_path, monkeypatch):
    from quwarts.eval import router_shared_read_run as rs

    monkeypatch.setitem(V3, "window_tokens", 1300)
    monkeypatch.setattr(rs, "BLANK_BASE", True)
    spec = toy_spec(tmp_path)
    (tmp_path / "docs" / "9.txt").write_text(LONG)
    queries = {r["query_id"]: r["sql"] for r in json.loads(spec.manifest.read_text())}
    calls = []

    def counted(prompt, metadata):
        calls.append(prompt)
        return responder(prompt, metadata)

    caller = fake_caller_factory(counted)(10**9)
    journal = tmp_path / "run" / "reads.jsonl"
    run_reads(spec, READS, {}, FIELDS, caller, journal, workers=2, long_documents="chain")
    db = tmp_path / "run" / "read_first_blank.db"
    rs.build_db(spec, READS, load_values(journal, FIELDS), FIELDS, queries, db, "replace")
    store = tmp_path / "run" / "provenance" / "provenance.db"
    M.capture(store, spec, READS, FIELDS, journal, db, queries)
    calls.clear()
    return {"spec": spec, "queries": queries, "store": store, "db": db, "calls": calls, "tmp": tmp_path,
            "caller": fake_caller_factory(counted)(10**9)}


def apply(run, overlay=None, policy="facts", budget=None, caller=None):
    return M.apply(run["store"], run["spec"], READS, FIELDS, run["queries"], overlay, policy,
                   caller or run["caller"], budget, workers=2, build=build)


def overlay(run, files: dict[str, str], deleted=()):
    root = run["tmp"] / f"overlay{len(list(run['tmp'].glob('overlay*')))}"
    (root / "c").mkdir(parents=True)
    for name, text in files.items():
        (root / "c" / name).write_text(text)
    if deleted:
        (root / "c" / "DELETED").write_text("\n".join(deleted))
    return root


def cell(db, doc, attr):
    conn = sqlite3.connect(db)
    (v,) = conn.execute(f'SELECT "{attr}" FROM c WHERE doc_id = ?', (doc,)).fetchone()
    conn.close()
    return v


def test_capture_records_modes_and_support(run):
    conn = sqlite3.connect(run["store"])
    modes = dict(conn.execute("SELECT doc, mode FROM documents"))
    assert modes["9.txt"] == "chain" and modes["1.txt"] == "single"
    (n,) = conn.execute("SELECT n_chunks FROM documents WHERE doc = '9.txt'").fetchone()
    assert n >= 3
    (support,) = conn.execute("SELECT support FROM cells WHERE doc = '9.txt' AND attr = 'verdict'").fetchone()
    assert json.loads(support) == [n - 1]  # the verdict is stated in the last chunk only


def test_no_change_is_idempotent(run):
    report = apply(run)
    assert report["status"] == "applied" and report.get("reads", 0) == 0
    assert report["cells_changed"] == 0 and report["queries_answer_changed"] == []
    assert not any(d["cells"] for d in M.diff_databases(run["db"], run["store"].parent / "maintained.db")["tables"].values())


def test_short_document_edit_reads_once_and_updates_queries(run):
    text = (run["tmp"] / "docs" / "3.txt").read_text().replace("2003", "2013")
    report = apply(run, overlay(run, {"3.txt": text}))
    assert report["reads"] == 1
    assert cell(run["store"].parent / "maintained.db", "3.txt", "hearing_year") == 2013
    assert report["cells_changed"] == 1 and report["queries_reexecuted"] == 2
    assert report["queries_answer_changed"] == ["q1"]  # q2 reads hearing_year, but its count is unchanged
    conn = sqlite3.connect(run["store"])
    old, new = conn.execute("SELECT old, new FROM history WHERE doc = '3.txt'").fetchone()
    assert (json.loads(old), json.loads(new)) == (2003, 2013)


def test_edit_inside_one_chunk_reads_that_chunk_and_cuts_off(run):
    old = LONG
    new = old.replace("item 150 of the record", "item 150 of this record")  # one more character
    exact = apply(run, overlay(run, {"9.txt": new}), policy="exact")
    assert exact["reads"] == 2 and exact["reads_of_kept_chunks"] == 1  # the note's wording changed once
    assert exact["cells_changed"] == 0 and exact["queries_reexecuted"] == 0


def test_facts_policy_ignores_rewording_of_the_note(run):
    new = LONG.replace("item 150 of the record", "item 150 of this record")
    facts = apply(run, overlay(run, {"9.txt": new}), policy="facts")
    assert facts["reads"] == 1 and facts.get("reads_of_kept_chunks", 0) == 0


def test_delete_and_add_copy_of_known_document(run):
    report = apply(run, overlay(run, {"10.txt": LONG}, deleted=["8.txt"]))
    assert report.get("reads", 0) == 0  # every chunk of the copy is in the memo
    assert report["rows_deleted"] == 1 and report["rows_inserted"] == 1
    assert cell(run["store"].parent / "maintained.db", "10.txt", "verdict") == "Dismissed"


def test_budget_defers_and_flags(run):
    text = (run["tmp"] / "docs" / "3.txt").read_text().replace("2003", "2013")
    report = apply(run, overlay(run, {"3.txt": text}), budget=0)
    assert report["deferred_documents"] == ["c/3.txt"] and report["stale_documents"] == ["c/3.txt"]
    assert set(report["queries_flagged_stale"]) == {"q1", "q2"} and report["cells_changed"] == 0
    assert cell(run["store"].parent / "maintained.db", "3.txt", "hearing_year") == 2003


def test_realign_keeps_untouched_chunks():
    old = "".join(f"line {i}\n" for i in range(50))
    bounds, pos = [], 0
    for size in (100, 100, len(old) - 200):
        bounds.append((pos, pos + size))
        pos += size
    new = "NEW START\n" + old[:150] + "edited " + old[150:]
    chunks, kept = M.realign(old, bounds, new, 1000)
    assert "".join(chunks) == new
    assert kept == [None, 0, None, 2]


def test_carry_facts():
    assert S.carry_facts("This document is about Acme Corp, year 2021, in USD.") == \
        S.carry_facts("The document concerns Acme Corp; USD, for 2021.")
    assert S.carry_facts("Acme Corp 2021") != S.carry_facts("Acme Corp 2022")


def _noted(run):
    def noted(prompt, metadata):
        out = json.loads(responder(prompt, metadata))
        if "PART " in prompt and "Intro" in prompt:  # the note carries an introduction forward once it has seen one
            out["context_for_next_part"] += " Intro"
        run["calls"].append(prompt)
        return json.dumps(out)

    return fake_caller_factory(noted)(10**9)


def _chunks_of_9(run):
    conn = sqlite3.connect(run["store"])
    (n,) = conn.execute("SELECT n_chunks FROM documents WHERE doc = '9.txt'").fetchone()
    conn.close()
    return n


def test_facts_policy_ripples_when_the_note_states_a_new_fact(run):
    n = _chunks_of_9(run)
    new = "Intro paragraph.\n" * 30 + LONG
    r = M.apply(run["store"], run["spec"], READS, FIELDS, run["queries"], overlay(run, {"9.txt": new}), "facts",
                _noted(run), None, workers=1, build=build)
    assert r["reads"] == n + 1 and r["cells_changed"] == 0


def test_answers_policy_ends_the_ripple_at_the_probe(run):
    new = "Intro paragraph.\n" * 30 + LONG
    r = M.apply(run["store"], run["spec"], READS, FIELDS, run["queries"], overlay(run, {"9.txt": new}), "answers",
                _noted(run), None, workers=1, build=build)
    assert r["reads"] == 2 and r["answer_cutoffs"] == 1 and r["cells_changed"] == 0


def test_attribution_keeps_unexplained_changes(run):
    def noisy(prompt, metadata):
        out = json.loads(responder(prompt, metadata))
        if "extra remark" in prompt:
            out["fields"]["verdict"] = "Approved"  # read noise: nothing in the edit says so
        return json.dumps(out)

    caller = fake_caller_factory(noisy)(10**9)
    text = (run["tmp"] / "docs" / "4.txt").read_text() + "An extra remark about the weather.\n"
    report = M.apply(run["store"], run["spec"], READS, FIELDS, run["queries"], overlay(run, {"4.txt": text}), "answers",
                     caller, None, workers=1, build=build, attribute=True)
    assert report["changes_kept_unexplained"] == 1 and report["cells_changed"] == 0
    text = (run["tmp"] / "docs" / "5.txt").read_text().replace("2005", "2015")
    report = M.apply(run["store"], run["spec"], READS, FIELDS, run["queries"], overlay(run, {"5.txt": text}), "answers",
                     caller, None, workers=1, build=build, attribute=True)
    assert report["changes_explained"] == 1
    assert cell(run["store"].parent / "maintained.db", "5.txt", "hearing_year") == 2015


def test_maintained_database_edited_outside_apply_is_refused(run):
    conn = sqlite3.connect(run["store"].parent / "maintained.db")
    conn.execute("UPDATE c SET hearing_year = 1 WHERE doc_id = '1.txt'")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError):
        apply(run)

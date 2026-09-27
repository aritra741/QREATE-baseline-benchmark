"""Synthetic-edit evaluation of provenance-based maintenance (AUDIT: compares against fresh reads).

On copies of a corpus's provenance store, apply one kind of edit to a seeded sample of documents
(the source files are never modified; edits live in an overlay folder) and maintain the database with
each policy. Edit kinds:

* ``irrelevant``   a neutral paragraph inserted mid-document: nothing should change
* ``value``        a value the database holds, stated verbatim in the document, is replaced everywhere by
                   another value (another document's value for text; x1.37 for numbers, +3 for years)
* ``prepend``      a long neutral block at the start (shifts every position in the document)
* ``append``       a long neutral block at the end
* ``evidence``     every line stating a held value is deleted
* ``copy_delete``  one document deleted, a copy of another added under a new name

Reference: every edited document read again from scratch by the same system (fresh chunking, no
memo). Reported per kind and policy: reads and tokens against reading the edited documents from
scratch; cells changed; for ``value``, the share of edited cells that take the new value (maintained
and reference); agreement of the maintained cells with the reference; queries re-executed and queries
whose answers changed.

    python -m quwarts.eval.provenance_edits --corpus finan --prepare
    python -m quwarts.eval.provenance_edits --corpus finan --run --deadline 100   # repeat until done
    python -m quwarts.eval.provenance_edits --corpus finan --report
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from quwarts.core.router.registry import RESULTS

KINDS = ["irrelevant", "value", "prepend", "append", "evidence", "copy_delete"]
POLICIES = ["exact", "facts", "answers"]  # model-calling policies
VARIANTS = POLICIES + [f"{p}+attr" for p in POLICIES]  # +attr: the same reads, changes committed only if explained
SAMPLE = {"finan": 6, "legal": 12}
SEED = 20260928
NEUTRAL = ("The following section is provided for general information only. It does not modify, qualify or "
           "replace any statement made elsewhere in this document, and readers should refer to the relevant "
           "sections for complete details.")
ROOT = RESULTS / "provenance_eval"
TAG = ""  # "" is the development sample; another tag draws a fresh sample into its own folder


def _root(corpus: str) -> Path:
    return ROOT / (corpus + (f"_{TAG}" if TAG else ""))


def _ctx(corpus: str):
    from quwarts.eval.router_provenance import context

    return context(corpus)


def _store_rows(base: Path):
    conn = sqlite3.connect(base / "provenance.db")
    docs = {(t, d): (m, n) for t, d, m, n in conn.execute("SELECT tbl, doc, mode, n_chunks FROM documents")}
    cells = [(t, d, a, json.loads(v)) for t, d, a, v in conn.execute("SELECT tbl, doc, attr, value FROM cells")]
    conn.close()
    return docs, cells


def _number_surfaces(v: float) -> list[str]:
    out = []
    if float(v).is_integer():
        out += [f"{int(v):,}", f"{int(v)}"]
    else:
        out += [f"{v:,.2f}", f"{v:.2f}", f"{v}"]
    return out


def _find(text: str, surface: str) -> list[re.Match]:
    return list(re.finditer(r"(?<![\w.,])" + re.escape(surface) + r"(?![\w]|[.,]\d)", text))


def _new_number(v: float, surface: str, is_int: bool) -> str:
    if is_int and 1900 <= v <= 2100:
        new = int(v) + 3
    else:
        new = v * 1.37
    if "," in surface or "." not in surface:
        new_s = f"{round(new):,}" if "," in surface else f"{round(new)}"
    else:
        new_s = f"{new:,.2f}" if "," in surface else f"{new:.2f}"
    return new_s


def prepare(corpus: str) -> dict[str, Any]:
    from quwarts.core.router.executor import commit_value

    spec, fields, reads, queries, workload, out = _ctx(corpus)
    base = out / "provenance"
    docs, cells = _store_rows(base)
    rng = random.Random(f"{SEED}:{corpus}" + (f":{TAG}" if TAG else ""))
    paths = {(t.sql_name, p.name): p for t in spec.tables for p in sorted(t.doc_dir.glob("*.txt"))}
    by_col: dict[tuple[str, str], list] = {}
    for t, d, a, v in cells:
        by_col.setdefault((t, a), []).append((d, v))
    n = SAMPLE[corpus]
    used: set = set()

    def sample(pool: list, k: int) -> list:
        chain = [x for x in pool if docs[x][0] == "chain" and x not in used]
        single = [x for x in pool if docs[x][0] == "single" and x not in used]
        rng.shuffle(chain)
        rng.shuffle(single)
        pick = chain[: k // 2] + single[: k - k // 2]
        pick += [x for x in chain + single if x not in pick][: k - len(pick)]
        used.update(pick)
        return pick

    def held_value(key) -> tuple | None:
        """A cell of this document whose value is stated verbatim in its text (text >= 4 chars,
        numbers >= 4 digits, no allowed-value fields, no negatives)."""

        t, d = key
        text = paths[key].read_text(errors="replace")
        options = []
        for (tt, dd, a, v) in cells:
            if (tt, dd) != key or v is None:
                continue
            f = fields.get(f"{t}.{a}")
            if f is None or f.choices:
                continue
            if isinstance(v, str):
                surfaces = [v] if len(v) >= 4 and "||" not in v else []
            elif isinstance(v, (int, float)) and v > 0:
                surfaces = [s for s in _number_surfaces(float(v)) if len(re.sub(r"\D", "", s)) >= 4]
            else:
                surfaces = []
            for s in surfaces:
                if _find(text, s):
                    options.append((a, v, s))
                    break
        return rng.choice(sorted(options, key=str)) if options else None

    all_keys = sorted(k for k in docs if k in paths)
    plan: dict[str, Any] = {}
    for kind in KINDS:
        folder = _root(corpus) / kind
        if folder.exists():
            shutil.rmtree(folder)
        edits = []
        if kind in ("value", "evidence"):
            pool = [k for k in all_keys if k not in used]
            rng.shuffle(pool)
            for key in pool:
                if len(edits) >= n:
                    break
                got = held_value(key)
                if got is None:
                    continue
                attr, value, surface = got
                f = fields[f"{key[0]}.{attr}"]
                text = paths[key].read_text(errors="replace")
                if kind == "value":
                    if isinstance(value, str):
                        others = sorted({v for d, v in by_col[(key[0], attr)] if isinstance(v, str) and len(v) >= 4
                                         and v != value and not _find(text, v) and "||" not in v})
                        if not others:
                            continue
                        new_surface = rng.choice(others)
                    else:
                        new_surface = _new_number(float(value), surface, f.value_type == "int")
                    new_text = re.sub(r"(?<![\w.,])" + re.escape(surface) + r"(?![\w]|[.,]\d)", new_surface, text)
                    expected = commit_value(new_surface, f)
                    edits.append({"table": key[0], "doc": key[1], "attr": attr, "old": value, "surface": surface,
                                  "new_surface": new_surface, "expected": expected,
                                  "occurrences": len(_find(text, surface)), "text": new_text})
                else:
                    lines = text.splitlines(keepends=True)
                    kept = [ln for ln in lines if not _find(ln, surface)]
                    edits.append({"table": key[0], "doc": key[1], "attr": attr, "old": value, "surface": surface,
                                  "lines_deleted": len(lines) - len(kept), "text": "".join(kept)})
                used.add(key)
        elif kind == "copy_delete":
            picks = sample(all_keys, 2 * n)
            for a, b in zip(picks[:n], picks[n:]):
                edits.append({"table": a[0], "doc": a[1], "deleted": True})
                edits.append({"table": b[0], "doc": b[1].replace(".txt", "_copy.txt"), "copy_of": b[1],
                              "text": paths[b].read_text(errors="replace")})
        else:
            for key in sample(all_keys, n):
                text = paths[key].read_text(errors="replace")
                block = "\n\n".join([NEUTRAL] * 12) + "\n\n"
                if kind == "irrelevant":
                    lines = text.splitlines(keepends=True)
                    mid = len(lines) // 2
                    new_text = "".join(lines[:mid]) + "\n" + NEUTRAL + "\n\n" + "".join(lines[mid:])
                elif kind == "prepend":
                    new_text = block + text
                else:
                    new_text = text + ("" if text.endswith("\n") else "\n") + "\n" + block
                edits.append({"table": key[0], "doc": key[1], "text": new_text})
        for e in edits:
            layer = folder / "overlay" / e["table"]
            layer.mkdir(parents=True, exist_ok=True)
            if e.get("deleted"):
                with (layer / "DELETED").open("a") as h:
                    h.write(e["doc"] + "\n")
            else:
                (layer / e["doc"]).write_text(e["text"])
        for policy in VARIANTS:
            dest = folder / policy
            dest.mkdir(parents=True)
            shutil.copy2(base / "provenance.db", dest / "provenance.db")
            shutil.copy2(base / "maintained.db", dest / "maintained.db")
        (folder / "edits.json").write_text(json.dumps([{k: v for k, v in e.items() if k != "text"} for e in edits],
                                                      indent=1, default=str))
        plan[kind] = len(edits)
    return plan


def run(corpus: str, deadline: float, workers: int) -> dict[str, Any]:
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.lineage import maintain as M
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.router.executor import run_reads
    from quwarts.core.router.registry import PROJECT
    from quwarts.eval.router_provenance import build

    spec, fields, reads, queries, workload, out = _ctx(corpus)
    load_env_file(PROJECT / ".env")
    stop = time.monotonic() + deadline
    done: dict[str, Any] = {}
    for kind in KINDS:
        folder = _root(corpus) / kind
        for variant in VARIANTS:
            policy, attribute = variant.split("+")[0], variant.endswith("+attr")
            report = folder / variant / "report.json"
            if report.exists():
                done[f"{kind}/{variant}"] = "done"
                continue
            if attribute:
                if not (folder / policy / "report.json").exists():
                    continue
                # The same reads as the policy's run: copy its memo, so the attributed run makes no calls.
                conn = sqlite3.connect(folder / variant / "provenance.db")
                conn.execute("ATTACH DATABASE ? AS src", (str(folder / policy / "provenance.db"),))
                conn.execute("INSERT OR IGNORE INTO reads SELECT * FROM src.reads")
                conn.commit()
                conn.execute("DETACH DATABASE src")
                conn.close()
            left = stop - time.monotonic()
            if left < 10:
                return {**done, "status": "incomplete"}
            caller = make_caller(TokenLedger(theta=10**12), max_tokens=600)
            r = M.apply(folder / variant / "provenance.db", spec, reads, fields, queries, folder / "overlay", policy,
                        caller, None, workers, left, workload, build=build, attribute=attribute)
            policy = variant
            if r["status"] != "applied":
                return {**done, f"{kind}/{policy}": r.get("reads", 0), "status": "incomplete"}
            report.write_text(json.dumps(r, indent=1, default=str))
            done[f"{kind}/{policy}"] = "applied"
    # Reference: the edited documents read from scratch by the same system.
    for kind in KINDS:
        folder = _root(corpus) / kind
        if (folder / "reference_done").exists():
            continue
        edits = json.loads((folder / "edits.json").read_text())
        current = {t.sql_name: {} for t in spec.tables}
        for e in edits:
            if not e.get("deleted") and kind != "copy_delete":
                current[e["table"]][e["doc"]] = folder / "overlay" / e["table"] / e["doc"]
        if not any(current.values()):
            (folder / "reference_done").write_text("")
            continue
        left = stop - time.monotonic()
        if left < 10:
            return {**done, "status": "incomplete"}
        view, root = M._view(spec, current)
        caller = make_caller(TokenLedger(theta=10**12), max_tokens=600)
        stats = run_reads(view, reads, {}, fields, caller, folder / "reference.jsonl", workers, long_documents="chain",
                          deadline=left)
        shutil.rmtree(root, ignore_errors=True)
        if stats.get("stopped_at_deadline") or stats.get("exhausted"):
            return {**done, "status": "incomplete"}
        (folder / "reference_done").write_text(json.dumps(stats))
    return {**done, "status": "complete"}


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(a)))
    return str(a).strip().casefold() == str(b).strip().casefold()


def report(corpus: str) -> dict[str, Any]:
    from quwarts.core.lineage import store as S
    from quwarts.core.retrieve_extract.tokens import count_tokens
    from quwarts.core.router import chunked
    from quwarts.core.router.context_probe import V3
    from quwarts.core.router.executor import commit_value, load_values

    spec, fields, reads, queries, workload, out = _ctx(corpus)
    base_db = out / "provenance" / "maintained.db"
    window = int(V3["window_tokens"])
    run_tokens = json.loads((out / "score_blank.json").read_text())["read_tokens"]
    result: dict[str, Any] = {"corpus": corpus, "run_read_tokens": run_tokens, "queries": len(queries), "kinds": {}}

    def db_cells(db: Path, docs: set) -> dict:
        conn = sqlite3.connect(db)
        out_ = {}
        for read in reads:
            for a in read.attributes:
                for d, v in conn.execute(f'SELECT doc_id, "{a}" FROM "{read.table}"'):
                    if (read.table, d) in docs:
                        out_[(read.table, d, a)] = v
        conn.close()
        return out_

    base_keys = {k for (k,) in sqlite3.connect(out / "provenance" / "provenance.db").execute("SELECT read_key FROM reads")}

    def new_reads(store: Path) -> tuple[int, int]:
        """Reads this maintenance made: memo rows the copy has and the base store does not (robust to
        resumed runs and to documents sharing a chunk)."""

        conn = sqlite3.connect(store)
        rows = [t for k, t in conn.execute("SELECT read_key, tokens FROM reads") if k not in base_keys]
        conn.close()
        return len(rows), sum(rows)

    for kind in KINDS:
        folder = _root(corpus) / kind
        edits = json.loads((folder / "edits.json").read_text())
        edited = {(e["table"], e["doc"]) for e in edits if not e.get("deleted")}
        ref_values = {}
        if (folder / "reference.jsonl").exists():
            for (table, _ctx_), docs in load_values(folder / "reference.jsonl", fields).items():
                for d, vals in docs.items():
                    for a, v in vals.items():
                        ref_values[(table, d, a)] = commit_value(v, fields[f"{table}.{a}"])
        scratch_reads, scratch_tokens = 0, 0
        for e in edits:
            if e.get("deleted") or kind == "copy_delete":
                continue
            text = (folder / "overlay" / e["table"] / e["doc"]).read_text()
            pieces = [text] if count_tokens(text) <= window else chunked.split_chunks(text, chunked.chunk_tokens(window))
            scratch_reads += len(pieces)
            scratch_tokens += sum(count_tokens(p) for p in pieces) + 1300 * len(pieces)
        old = db_cells(base_db, edited)
        row: dict[str, Any] = {"documents": len(edited), "from_scratch_reads": scratch_reads,
                               "from_scratch_tokens_estimate": scratch_tokens}
        if ref_values:
            row["reference_vs_old_agreement"] = round(sum(_same(old.get(k), v) for k, v in ref_values.items()) / len(ref_values), 3)
        for policy in VARIANTS:
            if not (folder / policy / "report.json").exists():
                continue
            rep = json.loads((folder / policy / "report.json").read_text())
            new = db_cells(folder / policy / "maintained.db", edited)
            n_reads, n_tokens = new_reads(folder / policy.split("+")[0] / "provenance.db")
            r = {"reads": n_reads, "read_tokens": n_tokens, "answer_cutoffs": rep.get("answer_cutoffs", 0),
                 "changes_kept_unexplained": rep.get("changes_kept_unexplained", 0), "cells_changed": rep["cells_changed"],
                 "rows_deleted": rep["rows_deleted"], "rows_inserted": rep["rows_inserted"],
                 "queries_reexecuted": rep["queries_reexecuted"], "queries_answer_changed": len(rep["queries_answer_changed"]),
                 "edited_cells_changed": sum(not _same(old.get(k), new.get(k)) for k in new if k in old)}
            if ref_values:
                r["agreement_with_reference"] = round(sum(_same(new.get(k), v) for k, v in ref_values.items()) / len(ref_values), 3)
            if kind == "value":
                r["took_new_value"] = sum(_same(new.get((e["table"], e["doc"], e["attr"])), e["expected"]) for e in edits)
            if kind == "evidence":
                r["target_changed"] = sum(not _same(new.get((e["table"], e["doc"], e["attr"])), e["old"]) for e in edits)
            row[policy] = r
        if kind == "value" and ref_values:
            row["reference_took_new_value"] = sum(_same(ref_values.get((e["table"], e["doc"], e["attr"])), e["expected"]) for e in edits)
        if kind == "evidence" and ref_values:
            row["reference_target_changed"] = sum(not _same(ref_values.get((e["table"], e["doc"], e["attr"])), e["old"]) for e in edits)
        if kind in ("value", "evidence"):
            row["edited_cells"] = len(edits)
        result["kinds"][kind] = row
    (_root(corpus) / "report.json").write_text(json.dumps(result, indent=1))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True, choices=sorted(SAMPLE))
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--deadline", type=float, default=100)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--tag", default="", help="sample tag: a fresh seeded sample in its own folder")
    args = parser.parse_args(argv)
    global TAG
    TAG = args.tag
    if args.prepare:
        print(json.dumps(prepare(args.corpus)))
    if args.run:
        print(json.dumps(run(args.corpus, args.deadline, args.workers)))
    if args.report:
        print(json.dumps(report(args.corpus), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

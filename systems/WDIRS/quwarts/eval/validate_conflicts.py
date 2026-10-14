"""Check a file of representation-conflict question groups against the correct data.

Each question has a NATURAL query, written the way an analyst or a text-to-SQL tool would write it (this is all a
system sees), and an ANSWER KEY: the SQL that computes the correct answer from the correct data, which stores values
as the documents state them. The answer key holds the post-processing the question means (a renamed franchise counted
under its current name, an artist's first-listed field, a country's region); the system must store the data in a
form that makes its natural query give that answer. Questions of a group use one column and need it in different
stored forms. Each FORM is one SQL UPDATE of that column (the form a question needs, stored in place of the raw value);
"raw" (the values as stated) is always a candidate form too.

A group passes when:
- every question scores 1.0 (exact) under at least one form (its natural query on that form = its answer key), and
  under every FORM declared for it;
- no single form makes every question of the group score 1.0 (the conflict is real: one stored form cannot serve all);
- every answer key passes the standard checks (runs on the correct data, non-empty, no empty group keys or cells,
  scores 1.0 against itself); every natural query runs, returns the answer key's columns, and passes the realism rules.

File format (Query/Realistic/conflict/<corpus>.sql):
    -- GROUP G1: <one line: the shared column and the form each question needs>
    -- TYPE: list-vs-one | fine-vs-coarse | join-spelling | number-vs-text
    -- COLUMN: table.column
    -- FORM G1a: UPDATE <table> SET <column> = ... ;     (one line; omit for a question that needs the stated value)
    -- G1a: <question>
    SELECT ... ;                                         (natural query)
    -- KEY G1a:
    SELECT ... ;                                         (answer key)

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.validate_conflicts <corpus> <file.sql> [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import tempfile
from pathlib import Path

TYPES = ("list-vs-one", "fine-vs-coarse", "join-spelling", "number-vs-text")


def parse(path: Path) -> list[dict]:
    """Groups with their questions: {id, question, sql (natural), key (answer key)}."""
    groups, cur, target, buf = [], None, None, []

    def flush():
        nonlocal target, buf
        if target is not None and buf:
            q, field = target
            q[field] = " ".join(buf).strip().rstrip(";").strip() + ";"
        target, buf = None, []

    for line in path.read_text().splitlines() + ["-- END"]:
        s = line.strip()
        if not s.startswith("--"):
            if s and target is not None:
                buf.append(s)
            continue
        flush()
        if m := re.match(r"--\s*GROUP\s+(G\w+):\s*(.*)", s):
            cur = {"id": m.group(1), "about": m.group(2), "type": None, "column": None, "forms": {}, "queries": []}
            groups.append(cur)
        elif cur is None:
            continue
        elif m := re.match(r"--\s*TYPE:\s*(.*)", s):
            cur["type"] = m.group(1).strip()
        elif m := re.match(r"--\s*COLUMN:\s*(\S+)", s):
            cur["column"] = m.group(1).strip()
        elif m := re.match(r"--\s*FORM\s+(G\w+):\s*(.*)", s):
            cur["forms"][m.group(1)] = m.group(2).strip().rstrip(";")
        elif m := re.match(r"--\s*KEY\s+(G\w+):?\s*$", s):
            q = next((x for x in cur["queries"] if x["id"] == m.group(1)), None)
            if q is not None:
                target = (q, "key")
        elif m := re.match(r"--\s*(G\d+[a-z]):\s*(.*)", s):
            q = {"id": m.group(1), "question": m.group(2).strip(), "sql": None, "key": None}
            cur["queries"].append(q)
            target = (q, "sql")
    return groups


def qid(c: str, q: str) -> str:
    return f"conflict:{c}#{q}"


def register(ctx, c: str, groups: list[dict]) -> list[str]:
    """Put the natural queries in the catalogue and their answer keys in the scorer's REFERENCE."""
    from quwarts.eval.exp_tau import REFERENCE

    ids = []
    for g in groups:
        for q in g["queries"]:
            ctx.catalog[qid(c, q["id"])] = q["sql"]
            REFERENCE[qid(c, q["id"])] = q["key"]
            ids.append(qid(c, q["id"]))
    return ids


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("file")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    from quwarts.eval import drift_live as D
    from quwarts.eval import validate_queries as V
    from quwarts.eval.exp_context import fields_of
    from quwarts.eval.exp_realism import audit
    from quwarts.eval.exp_tau import score_multi
    from spp.config_grid import _build_in_memory_db

    c = a.corpus
    groups = parse(Path(a.file))
    tmp = Path(tempfile.mkdtemp(dir="/scratch/general/vast/u1592362"))
    # 1. every answer key through the standard checker (runs, non-empty, no empty keys/cells, self-score 1.0)
    alias = {f"QC{i + 1}": q["id"] for i, q in enumerate(q for g in groups for q in g["queries"])}
    back = {v: k for k, v in alias.items()}
    flat = tmp / "keys.sql"
    flat.write_text("\n\n".join(f"-- {back[q['id']]}: {q['question']}\n{q['key'] or 'SELECT 1;'}" for g in groups for q in g["queries"]))
    vrep = tmp / "v.json"
    V.main([c, str(flat), "--role", "test", "--out", str(vrep)])
    vk = {alias[r["id"]]: r for r in json.loads(vrep.read_text())["queries"]}
    ctx = D.R.context(c)
    fields = fields_of(c)
    gold, _ = D.R.Scorer(c).gold()
    g_mem = _build_in_memory_db(gold)
    report, bad = [], 0
    for g in groups:
        register(ctx, c, [g])
        res = {"group": g["id"], "about": g["about"], "type": g["type"], "column": g["column"], "problems": [], "queries": {}, "scores": {}}
        if len(g["queries"]) < 2:
            res["problems"].append("a group needs at least two questions")
        if g["type"] not in TYPES:
            res["problems"].append(f"unknown TYPE {g['type']!r}")
        t, col = (g["column"] or ".").split(".", 1)
        for q in g["queries"]:
            info = {"question": q["question"], "natural": q["sql"], "key": q["key"]}
            res["queries"][q["id"]] = info
            if not q["sql"] or not q["key"]:
                res["problems"].append(f"{q['id']} needs a natural query and an answer key")
                continue
            k = vk.get(q["id"], {})
            info["key_rows"] = k.get("result_rows")
            if not k.get("ok"):
                res["problems"].append(f"{q['id']} answer key fails the query checker: {k.get('problems')}")
            try:
                ncols = [d[0].lower() for d in g_mem.execute(q["sql"]).description]
                kcols = [d[0].lower() for d in g_mem.execute(q["key"]).description]
                if ncols != kcols:
                    res["problems"].append(f"{q['id']} natural query returns {ncols}, answer key {kcols} (must match)")
            except sqlite3.Error as exc:
                res["problems"].append(f"{q['id']} natural query or key fails: {exc}")
            flags = audit(q["sql"], fields, {}, None)["unrealistic"]
            if flags:
                res["problems"].append(f"{q['id']} natural query breaks realism rules {flags}")
            info["natural_length"] = len(q["sql"])
        # 2. every candidate form (raw, each declared FORM): score every question under each
        forms = {"raw": None, **{f"FORM {o}": u for o, u in g["forms"].items()}}
        for name, upd in forms.items():
            db = tmp / f"{g['id']}_{name.replace(' ', '_')}.db"
            if db.exists():
                db.unlink()
            dst = sqlite3.connect(db)
            g_mem.backup(dst)
            changed = 0
            if upd:
                m = re.match(r"UPDATE\s+\"?(\w+)\"?\s+SET\s+\"?(\w+)\"?\s*=", upd, re.I)
                if not m or m.group(1).lower() != t.lower() or m.group(2).lower() != col.lower():
                    res["problems"].append(f"{name} must be one UPDATE of the group's COLUMN {g['column']}")
                    dst.close()
                    continue
                before = dict(dst.execute(f'SELECT rowid, "{col}" FROM "{t}"').fetchall())
                try:
                    dst.execute(upd)
                    dst.commit()
                except sqlite3.Error as exc:
                    res["problems"].append(f"{name} fails: {exc}")
                    dst.close()
                    continue
                after = dict(dst.execute(f'SELECT rowid, "{col}" FROM "{t}"').fetchall())
                changed = sum(1 for r in before if str(before[r]) != str(after.get(r)))
            dst.close()
            D.R.complete(c, db)
            ids = [q["id"] for q in g["queries"] if q["sql"] and q["key"]]
            sc = score_multi(c, [(qid(c, x), db) for x in ids])
            res["scores"][name] = {"rows_changed": changed, **{x: {"0%": sc[qid(c, x)].get(0.0), "20%": sc[qid(c, x)].get(0.2)} for x in ids}}
        ok = lambda f, x: (res["scores"].get(f, {}).get(x, {}).get("0%") or 0) >= 0.999  # noqa: E731
        for q in g["queries"]:
            if not any(ok(f, q["id"]) for f in res["scores"]):
                res["problems"].append(f"{q['id']} is answered by no form (its natural query never matches its answer key)")
            if f"FORM {q['id']}" in res["scores"] and not ok(f"FORM {q['id']}", q["id"]):
                res["problems"].append(f"FORM {q['id']} does not answer {q['id']}")
        for f in res["scores"]:
            if g["queries"] and all(ok(f, q["id"]) for q in g["queries"]):
                res["problems"].append(f"form '{f}' answers every question of the group: no conflict")
        for o in g["forms"]:
            if o not in {q["id"] for q in g["queries"]}:
                res["problems"].append(f"FORM {o} names no question of the group")
        bad += bool(res["problems"])
        report.append(res)
    summary = {"corpus": c, "groups": len(groups), "questions": sum(len(g["queries"]) for g in groups), "groups_with_problems": bad,
               "by_type": {ty: sum(g["type"] == ty for g in groups) for ty in {g["type"] for g in groups}}}
    text = json.dumps({"summary": summary, "groups": report}, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text)
        print("REPORT", json.dumps(summary))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def load(c: str, path: Path | None = None) -> dict[str, str]:
    """The collection's conflict queries {query id: natural SQL}; their answer keys go into the scorer's REFERENCE."""
    from quwarts.eval.exp_tau import EXP, REFERENCE

    path = path or EXP.parents[1] / "Query" / "Realistic" / "conflict" / f"{c}.sql"
    out = {}
    for g in parse(path):
        for q in g["queries"]:
            out[qid(c, q["id"])] = q["sql"]
            REFERENCE[qid(c, q["id"])] = q["key"]
    return out

"""What carries our system over DocETL?  Cumulative repairs of DocETL's per-query database with our system's
values, on queries both systems answered (no model calls).

DocETL builds each query's tables from its model's answers: a document whose answer is not a tool call ("No tool
calls") is skipped, so its row is missing; an answer of "unknown" (-1 or "") is stored as NULL. Our system keeps one row
per document whatever the model returns. Steps, each on top of the previous one, over the real columns the query
uses (SELECT aliases such as a CASE bucket excluded):
  rows    documents DocETL dropped get a row with our values
  empty   DocETL's NULL answers get our value
  values  every remaining answer gets our value (should give back about our score)
Also, from DocETL's database, one role at a time (grouped by, filtered on, aggregated, join key): every answer of
those columns gets our value, dropped rows included. Rows are matched by document (doc_id is bookkeeping only; no
query reads it). Reported per collection at 20% tolerance: DocETL's score, each step's score, ours, and the share of
the gap each step recovers.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_swap realistic|drift [corpus ...]
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import statistics as S
import sys
import tempfile
from pathlib import Path

import sqlglot
from sqlglot import exp

from quwarts.eval import drift_live as D
from quwarts.eval.exp_docetl_variation import catalogs, safe
from quwarts.eval.exp_profile import roles
from quwarts.eval.exp_tau import EXP, score_multi

CORPORA = ["cspaper", "player", "art", "med", "legal"]
QV = Path("/scratch/general/vast/u1592362/quwarts_exp/RW-qviews/RW-norereads-V3")
FV = Path("/scratch/local/u1592362/16208085/claude-1797948/-uufs-chpc-utah-edu-common-home-u1592362-Downloads-QREATE-baseline-benchmark/843aaf5f-bcf7-4ac2-9ba8-cbdca8cfe56b/scratchpad/tau_v3rule/fv")
STEPS = ["rows", "empty", "values"]
ROLES = ["grouped by", "filtered on", "aggregated", "join key"]


def stem(d) -> str:
    d = str(d)
    return d.rsplit(".", 1)[0] if d.endswith(".txt") else d


def used(sql: str) -> set[str]:
    """Every table column the query reads; SELECT aliases are not columns."""
    tree = sqlglot.parse_one(sql, read="sqlite")
    alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    single = next(iter(alias.values())) if len(set(alias.values())) == 1 else None
    names = {a.alias.lower() for a in tree.find_all(exp.Alias)}
    out = set()
    for c in tree.find_all(exp.Column):
        t = alias.get(c.table, c.table) if c.table else single
        if t and not (not c.table and c.name.lower() in names):
            out.add(f"{t}.{c.name}")
    return out


def real(cols: set[str], sql: str) -> set[str]:
    return cols & used(sql)


def ours_values(db: Path, t: str, a: str) -> dict | None:
    con = sqlite3.connect(db)
    try:
        return {stem(d): v for d, v in con.execute(f'SELECT doc_id, "{a}" FROM "{t}"')}
    except sqlite3.Error:
        return None
    finally:
        con.close()


def repair(src: Path, dst: Path, ours: Path, cols: set[str], add_rows: bool, fill_empty: bool, replace: bool) -> None:
    shutil.copy2(src, dst)
    con = sqlite3.connect(dst)
    by_table: dict[str, dict[str, dict]] = {}
    for col in cols:
        t, a = col.split(".", 1)
        v = ours_values(ours, t, a)
        if v is not None:
            by_table.setdefault(t, {})[a.lower()] = v
    for t, attrs in by_table.items():
        try:
            have = {r[1].lower() for r in con.execute(f'PRAGMA table_info("{t}")')}
        except sqlite3.Error:
            continue
        if not have:
            continue
        for a in attrs:
            if a not in have:
                con.execute(f'ALTER TABLE "{t}" ADD COLUMN "{a}"')
        present = {stem(d): d for d, in con.execute(f'SELECT doc_id FROM "{t}"')}
        if add_rows:
            docs = set().union(*(v.keys() for v in attrs.values()))
            for d in sorted(docs - set(present)):
                names = ["doc_id", *attrs]
                con.execute(f'INSERT INTO "{t}" ({", ".join(chr(34) + n + chr(34) for n in names)}) VALUES ({", ".join("?" * len(names))})',
                            (f"{d}.txt", *(attrs[a].get(d) for a in attrs)))
        for a, vals in attrs.items():
            for s, d in present.items():
                if replace:
                    con.execute(f'UPDATE "{t}" SET "{a}" = ? WHERE doc_id = ?', (vals.get(s), d))
                elif fill_empty and vals.get(s) is not None:
                    con.execute(f'UPDATE "{t}" SET "{a}" = ? WHERE doc_id = ? AND "{a}" IS NULL', (vals.get(s), d))
    con.commit()
    con.close()


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    which, corpora = args[0], args[1:] or CORPORA
    name = which if corpora == CORPORA else f"{which}_{'_'.join(corpora)}"
    out = {}
    for c in corpora:
        ctx = D.R.context(c)
        cat = catalogs(c)
        root = EXP.parent / ("docetl_realistic_ollama" if which == "realistic" else "docetl_drift_ollama") / c
        per = json.loads((root / "per_query.json").read_text())
        if which == "realistic":
            recs = [json.loads(x) for x in (EXP / "RW-norereads-V3" / "live" / c / "streams" / "fixed4-realistic_100.jsonl").read_text().splitlines() if x.strip()]
            ours_db = {r["qid"]: QV / c / "fixed4-realistic_100" / f"{r['pos']:04d}.db" for r in recs}
        else:
            tests = set(json.loads((EXP.parent / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json").read_text())["test"])
            view = FV / f"{c}_V3" / "served.view.db"
            ours_db = {q: view for q in tests}
        qs = [q for q in per if q in ours_db and ours_db[q].exists() and cat.get(q) and (root / "db" / f"{safe(q)}.db").exists()]
        for q in qs:
            ctx.catalog.setdefault(q, cat[q])
        tmp = Path(tempfile.mkdtemp(dir="/scratch/general/vast/u1592362"))
        items = {"docetl": [(q, root / "db" / f"{safe(q)}.db") for q in qs], "ours": []}
        for q in qs:  # our table, completed like DocETL's (predicate signature columns)
            o = tmp / f"ours_{safe(q)}.db"
            shutil.copy2(ours_db[q], o)
            D.R.complete(c, o)
            items["ours"].append((q, o))
        for i, step in enumerate(STEPS):
            items[step] = []
            for q in qs:
                dst = tmp / f"{step}_{safe(q)}.db"
                repair(root / "db" / f"{safe(q)}.db", dst, ours_db[q], used(cat[q]), True, i >= 1, i >= 2)
                items[step].append((q, dst))
        for role in ROLES:
            items[role] = []
            for q in qs:
                dst = tmp / f"{role.replace(' ', '_')}_{safe(q)}.db"
                repair(root / "db" / f"{safe(q)}.db", dst, ours_db[q], real(roles(cat[q])[role], cat[q]), True, True, True)
                items[role].append((q, dst))
        sc = {k: score_multi(c, v) for k, v in items.items()}
        gap = sum(sc["ours"][q][0.2] - sc["docetl"][q][0.2] for q in qs)
        mean = lambda k: round(S.mean(sc[k][q][0.2] for q in qs), 4)  # noqa: E731
        res = {"queries": len(qs), "docetl_20": mean("docetl"), "ours_20": mean("ours"), "steps": {}, "roles": {}}
        prev = "docetl"
        for step in STEPS:
            d = sum(sc[step][q][0.2] - sc[prev][q][0.2] for q in qs)
            res["steps"][step] = {"score": mean(step), "share_of_gap": round(d / gap, 3) if gap else None}
            prev = step
        for role in ROLES:
            d = sum(sc[role][q][0.2] - sc["docetl"][q][0.2] for q in qs)
            res["roles"][role] = {"queries_with_role": sum(bool(roles(cat[q])[role]) for q in qs), "score": mean(role),
                                  "share_of_gap": round(d / gap, 3) if gap else None}
        res["per_query"] = {q: {k: round(sc[k][q][0.2], 3) for k in ["docetl", *STEPS, "ours"]} for q in qs}
        out[c] = res
        print(c, json.dumps({k: v for k, v in res.items() if k != "per_query"}), flush=True)
        shutil.rmtree(tmp, ignore_errors=True)
    dest = EXP / "WHY" / "swap"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / f"{name}.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

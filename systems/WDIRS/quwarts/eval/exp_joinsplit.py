"""The benchmark's join split (Query/<Corpus>/Join/join_queries.sql: binary and multi-table joins returning rows, no
aggregation), on our system's final tables. No model calls; only the queries whose columns our tables hold.

Per query:
  - pair recall / precision: the (document, document[, document]) tuples the join links in the correct data against
    those it links in our table (doc ids identify rows, so this measures the join alone, not the projected values);
  - result rows: the query's output rows matched to the correct output (numbers within 0/5/10/20%, text case-blind).
For multi-table joins, the observed tuple recall against the product of its hops' recalls (prediction: errors
compound, so recall multiplies). Per join key: its profile (surface forms per entity in the correct data, our exact
accuracy, the share of left rows whose key finds a match).

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_joinsplit <served tables dir>
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics as S
import sys
from collections import Counter
from pathlib import Path

import sqlglot
from sqlglot import exp

from quwarts.core.adapt import catalogue as K
from quwarts.core.router.comparator import as_number, is_null
from quwarts.eval import drift_live as D
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_tau import EXP

QDIR = EXP.parents[1] / "Query"
SPLITS = {"player": "Player/Join/join_queries.sql", "med": "Med/Join/join_queries.sql"}
RUNS = ["V3", "V3-rep1", "V3-rep2"]
TOLS = (0.0, 0.05, 0.10, 0.20)


def load_queries(path: Path) -> list[dict]:
    out, cat = [], None
    for block in re.split(r";\s*\n", path.read_text()):
        for line in block.splitlines():
            m = re.match(r"--\s*Query\s*(\d+):\s*(\w+)\s*\(([^)]*)\)", line)
            if m:
                cat = (int(m.group(1)), m.group(2), m.group(3).replace(" ", ""))
        sql = "\n".join(x for x in block.splitlines() if not x.strip().startswith("--")).strip()
        if sql.upper().startswith("SELECT") and cat:
            out.append({"n": cat[0], "category": cat[1], "tables": cat[2], "sql": sql})
    return out


def stem(d) -> str:
    d = str(d)
    return d.rsplit(".", 1)[0] if d.endswith(".txt") else d


def joins_of(sql: str) -> list[tuple[str, str, str, str]]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    hops = []
    for j in tree.find_all(exp.Join):
        on = j.args.get("on")
        if isinstance(on, exp.EQ):
            a, b = on.left, on.right
            hops.append((alias.get(a.table, a.table), a.name, alias.get(b.table, b.table), b.name))
    return hops


def tuples_ours(con, sql: str) -> set:
    tree = sqlglot.parse_one(sql, read="sqlite")
    sel = tree.find(exp.Select)
    tabs = [t.alias_or_name for t in tree.find_all(exp.Table)]
    sel.set("expressions", [sqlglot.parse_one(f"{t}.doc_id", read="sqlite") for t in tabs])
    return {tuple(stem(x) for x in r) for r in con.execute(sel.sql(dialect="sqlite"))}


def tuples_gold(gold: dict, sql: str) -> set:
    """The same join evaluated on the correct values (SQL '=' semantics: exact strings)."""
    hops = joins_of(sql)
    tree = sqlglot.parse_one(sql, read="sqlite")
    order = [t.name for t in tree.find_all(exp.Table)]
    rows = {t: {stem(d): r for d, r in gold.get(t, {}).items()} for t in order}
    cur = [{order[0]: d} for d in rows[order[0]]]
    for lt, lc, rt, rc in hops:
        new_t, old_t, nc, oc = (rt, lt, rc, lc) if rt not in cur[0] else (lt, rt, lc, rc)
        index = {}
        for d, r in rows[new_t].items():
            v = r.get(nc)
            if not is_null(v):
                index.setdefault(str(v), []).append(d)
        nxt = []
        for t in cur:
            v = rows[old_t][t[old_t]].get(oc)
            for d in index.get(str(v), []) if not is_null(v) else []:
                nxt.append({**t, new_t: d})
        cur = nxt
        if not cur:
            break
    return {tuple(t[x] for x in order) for t in cur if len(t) == len(order)}


def row_match(pred: list, gold: list, tol: float) -> tuple[float, float]:
    def same(a, b):
        if is_null(a) and is_null(b):
            return True
        if is_null(a) or is_null(b):
            return False
        if as_number(a) is not None and as_number(b) is not None:
            return correct(a, b, tol)
        return K.norm(a) == K.norm(b)

    left = list(gold)
    hit = 0
    for p in pred:
        for i, g in enumerate(left):
            if len(p) == len(g) and all(same(x, y) for x, y in zip(p, g)):
                hit += 1
                left.pop(i)
                break
    return (hit / len(gold) if gold else 1.0), (hit / len(pred) if pred else (1.0 if not gold else 0.0))


def main(argv=None) -> int:
    from spp.config_grid import _build_in_memory_db

    fv = Path((argv or sys.argv[1:])[0])
    out = {}
    for c, rel in SPLITS.items():
        qs = load_queries(QDIR / rel)
        gold_tables, _ = D.R.Scorer(c).gold()
        gconn = _build_in_memory_db(gold_tables)
        gdoc = gold_by_doc(c)
        cons = {r: sqlite3.connect(fv / f"{c}_{r}" / "served.db") for r in RUNS if (fv / f"{c}_{r}" / "served.db").exists()}
        have = {t: {r[1] for r in cons["V3"].execute(f'PRAGMA table_info("{t}")')} for (t,) in cons["V3"].execute("SELECT name FROM sqlite_master WHERE type='table'")}
        res = []
        hop_recall = {}
        for q in qs:
            tree = sqlglot.parse_one(q["sql"], read="sqlite")
            alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
            if any(col.name not in have.get(alias.get(col.table, col.table), set()) for col in tree.find_all(exp.Column)):
                continue
            g = tuples_gold(gdoc, q["sql"])
            grows = [tuple(r) for r in gconn.execute(q["sql"]).fetchall()]
            per = []
            for r, con in cons.items():
                o = tuples_ours(con, q["sql"])
                prows = [tuple(x) for x in con.execute(q["sql"]).fetchall()]
                per.append({"pair_recall": len(o & g) / len(g) if g else None, "pair_precision": len(o & g) / len(o) if o else None,
                            **{f"row_recall_{t:.0%}": row_match(prows, grows, t)[0] for t in TOLS},
                            **{f"row_precision_{t:.0%}": row_match(prows, grows, t)[1] for t in TOLS}})
            m = lambda k: round(S.mean(x[k] for x in per if x[k] is not None), 3) if any(x[k] is not None for x in per) else None  # noqa: E731
            item = {"query": q["n"], "category": q["category"], "tables": q["tables"], "hops": [f"{a}.{b}={c_}.{d}" for a, b, c_, d in joins_of(q["sql"])],
                    "gold_pairs": len(g), "gold_rows": len(grows),
                    **{k: m(k) for k in per[0]}}
            res.append(item)
            if len(item["hops"]) == 1:
                hop_recall.setdefault(item["hops"][0], []).append(item["pair_recall"])
        for it in res:
            if len(it["hops"]) > 1 and all(h in hop_recall for h in it["hops"]):
                pred = 1.0
                for h in it["hops"]:
                    pred *= S.mean(x for x in hop_recall[h] if x is not None)
                it["pair_recall_predicted_by_product_of_hops"] = round(pred, 3)
        # key profiles
        keys = {}
        for h in {h for it in res for h in it["hops"]}:
            (lt, lc), (rt, rc) = [x.split(".") for x in h.split("=")]
            for t, col in ((lt, lc), (rt, rc)):
                vals = [r.get(col) for r in gdoc.get(t, {}).values() if not is_null(r.get(col))]
                acc = []
                for d, v in cons["V3"].execute(f'SELECT doc_id, "{col}" FROM "{t}"'):
                    gr = gdoc.get(t, {}).get(str(d)) or gdoc.get(t, {}).get(stem(d))
                    if gr is not None and col in gr:
                        acc.append((is_null(v) and is_null(gr[col])) or (not is_null(v) and not is_null(gr[col]) and correct(v, gr[col], 0.0)))
                keys[f"{t}.{col}"] = {"rows": len(vals), "distinct_values": len({str(v) for v in vals}),
                                      "our_exact_accuracy": round(sum(acc) / len(acc), 3) if acc else None}
        def items(v):
            return {K.norm(x) for x in str(v).split("||") if x.strip()} if not is_null(v) else set()

        match = {}
        for h in {h for it in res for h in it["hops"]}:
            (lt, lc), (rt, rc) = [x.split(".") for x in h.split("=")]
            for name, left, right in (("correct data", [r.get(lc) for r in gdoc.get(lt, {}).values()], [r.get(rc) for r in gdoc.get(rt, {}).values()]),
                                      ("our system", [r[0] for r in cons["V3"].execute(f'SELECT "{lc}" FROM "{lt}"')], [r[0] for r in cons["V3"].execute(f'SELECT "{rc}" FROM "{rt}"')])):
                left = [v for v in left if not is_null(v)]
                exact = {str(v) for v in right if not is_null(v)}
                ritems = set().union(*[items(v) for v in right]) if right else set()
                match.setdefault(h, {})[name] = {
                    "left_rows": len(left),
                    "exact_string_match": round(sum(str(v) in exact for v in left) / len(left), 3) if left else None,
                    "any_item_matches_case_blind": round(sum(bool(items(v) & ritems) for v in left) / len(left), 3) if left else None,
                    "left_values_that_are_lists": round(sum(len(items(v)) > 1 for v in left) / len(left), 3) if left else None}
        out[c] = {"queries": res, "keys": keys, "key_match": match}
        for con in cons.values():
            con.close()
        gconn.close()
    dest = EXP / "WHY" / "joinsplit"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    for c, v in out.items():
        print("==", c, "keys", json.dumps(v["keys"]))
        print("   key match", json.dumps(v["key_match"], indent=1))
        for it in v["queries"]:
            print(f"  q{it['query']:2d} {it['category']:16s} {'; '.join(it['hops']):60s} gold pairs {it['gold_pairs']:4d}  pair R {it['pair_recall']} P {it['pair_precision']}"
                  f"  pred {it.get('pair_recall_predicted_by_product_of_hops', '')}  rows R@0 {it['row_recall_0%']} R@20 {it['row_recall_20%']} P@20 {it['row_precision_20%']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Data profile against query features: which properties of the data a query touches explain its score.

Five collections are too few to separate collection-level traits, so the profile is taken per column (what a query
touches) and the comparison is made within collections. Per column used by a test query, from the data alone:
kind (list, number, category, yes/no, free text), share of blank correct answers, share of correct answers written
word for word in the document, distinct values per row, median document length of its table; and our system's
accuracy on it (run V3's final table, exact and 20%). Per query: the role of each column (aggregated, grouped by,
filtered on, join key), aggregate class, group size, joins. Outputs the profile, and the score of our system (and
DocETL) by the kind and accuracy of the column in each role. No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_profile <served tables dir>
"""

from __future__ import annotations

import json
import random
import sqlite3
import statistics as S
import sys
from collections import defaultdict
from pathlib import Path

import sqlglot
from sqlglot import exp

from quwarts.core.adapt import catalogue as K
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router.comparator import is_null
from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_live as D
from quwarts.eval.exp_aggtype import agg_class
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_tau import EXP
from quwarts.eval.exp_transfer import kind_of

CORPORA = ["cspaper", "player", "art", "med", "legal"]
SAMPLE = 120  # documents per table for text-based properties


def roles(sql: str) -> dict[str, set[str]]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    single = next(iter(alias.values())) if len(set(alias.values())) == 1 else None

    def cols(node):
        out = set()
        for c in node.find_all(exp.Column):
            t = alias.get(c.table, c.table) if c.table else single
            if t:
                out.add(f"{t}.{c.name}")
        return out

    r = {"aggregated": set(), "grouped by": set(), "filtered on": set(), "join key": set()}
    for a in tree.find_all(exp.AggFunc):
        r["aggregated"] |= cols(a)
    if tree.find(exp.Group):
        r["grouped by"] |= cols(tree.find(exp.Group))
    if tree.find(exp.Where):
        r["filtered on"] |= cols(tree.find(exp.Where))
    for j in tree.find_all(exp.Join):
        if j.args.get("on") is not None:
            r["join key"] |= cols(j.args["on"])
    return r


def column_profile(c: str, ctx, fields: dict, gold: dict, served: sqlite3.Connection, col: str) -> dict | None:
    t, a = col.split(".", 1)
    f = fields.get(col)
    gt = gold.get(t, {})
    if not gt:
        return None
    rows = [(d, g.get(a)) for d, g in gt.items() if a in g]
    if not rows:
        return None
    nonblank = [v for _, v in rows if not is_null(v)]
    rng = random.Random(f"{c}:{col}")
    docs = [d for d, _ in rows if d in ctx.docs.get(t, {}) or f"{d}.txt" in ctx.docs.get(t, {})]
    sample = rng.sample(docs, min(SAMPLE, len(docs)))
    verb, lens = [], []
    for d in sample:
        p = ctx.docs[t].get(d) or ctx.docs[t].get(f"{d}.txt")
        text = read_document(Path(p))
        lens.append(count_tokens(text))
        v = gt[d].get(a)
        if not is_null(v):
            verb.append(K.position_of(text.lower(), v) is not None)
    acc0 = acc20 = n = 0
    try:
        for d, v in served.execute(f'SELECT doc_id, "{a}" FROM "{t}"'):
            g = gt.get(str(d)) or gt.get(str(d).rsplit(".", 1)[0])
            if g is None or a not in g:
                continue
            n += 1
            gv = g[a]
            ok = lambda tol: (is_null(v) and is_null(gv)) or (not is_null(v) and not is_null(gv) and correct(v, gv, tol))  # noqa: E731
            acc0 += ok(0.0)
            acc20 += ok(0.2)
    except sqlite3.Error:
        pass
    return {"kind": kind_of(f) if f else "key or id", "rows": len(rows),
            "blank_share": round(1 - len(nonblank) / len(rows), 3),
            "written_in_text": round(sum(verb) / len(verb), 3) if verb else None,
            "distinct_per_row": round(len({K.norm(v) for v in nonblank}) / max(1, len(nonblank)), 3),
            "doc_tokens_median": int(S.median(lens)) if lens else None,
            "our_accuracy_exact": round(acc0 / n, 3) if n else None, "our_accuracy_20": round(acc20 / n, 3) if n else None}


def main(argv=None) -> int:
    fv = Path((argv or sys.argv[1:])[0])
    profile, queries = {}, []
    for c in CORPORA:
        ctx = D.R.context(c)
        fields = fields_of(c)
        gold = gold_by_doc(c)
        pq = json.loads((EXP / "WHY" / "tau" / f"{c}_per_query.json").read_text())
        ours, doc = pq["our system"], pq["DocETL"]["DocETL"]
        served = sqlite3.connect(fv / f"{c}_V3" / "served.db")
        gs = {r["qid"]: r["median_group"] for r in json.loads((EXP / "WHY" / "groupsize" / "summary.json").read_text())["queries"] if r["corpus"] == c}
        for q in doc:
            sql = ctx.catalog[q]
            r = roles(sql)
            for cols in r.values():
                for col in cols:
                    key = f"{c}:{col}"
                    if key not in profile:
                        profile[key] = column_profile(c, ctx, fields, gold, served, col)
            mean = lambda get: S.mean(get(x[q]) for x in ours.values())  # noqa: E731
            queries.append({"corpus": c, "qid": q, "class": agg_class(sql)["class"], "joins": agg_class(sql)["joins"],
                            "group_size": gs.get(q), "roles": {k: sorted(v) for k, v in r.items()},
                            "ours_20": mean(lambda x: x["0.2"]), "ours_0": mean(lambda x: x["0.0"]),
                            "ours_structure": mean(lambda x: x["structure"]), "ours_cell20": mean(lambda x: x["cell"]["0.2"]),
                            "docetl_20": doc[q]["0.2"], "docetl_structure": doc[q]["structure"]})
        served.close()

    def prof(c, col):
        return profile.get(f"{c}:{col}") or {}

    out = {"profile_by_corpus": {}, "by_role_and_kind": {}, "by_role_accuracy": {}, "joins": {}}
    for c in CORPORA:
        cols = {k.split(":", 1)[1]: v for k, v in profile.items() if k.startswith(c + ":") and v}
        kinds = defaultdict(int)
        for v in cols.values():
            kinds[v["kind"]] += 1
        num = lambda key: [v[key] for v in cols.values() if v.get(key) is not None]  # noqa: E731
        out["profile_by_corpus"][c] = {"columns_used": len(cols), "kinds": dict(kinds),
                                       "blank_share_median": round(S.median(num("blank_share")), 3),
                                       "written_in_text_median": round(S.median(num("written_in_text")), 3) if num("written_in_text") else None,
                                       "doc_tokens_median": int(S.median(num("doc_tokens_median"))),
                                       "our_accuracy_exact_median": round(S.median(num("our_accuracy_exact")), 3) if num("our_accuracy_exact") else None}
    # score by the kind of the column in each role (query counted once per kind present in that role)
    for role in ("aggregated", "grouped by", "filtered on", "join key"):
        grp = defaultdict(list)
        for qr in queries:
            kinds = {prof(qr["corpus"], col).get("kind") for col in qr["roles"][role]} - {None}
            if not qr["roles"][role]:
                kinds = {"(none: rows only)" if role == "aggregated" else "(none)"}
            for k in kinds:
                grp[(qr["corpus"], k)].append(qr)
        out["by_role_and_kind"][role] = {f"{c} | {k}": {"queries": len(v), "ours_20": round(S.mean(x["ours_20"] for x in v), 3),
                                                       "ours_structure": round(S.mean(x["ours_structure"] for x in v), 3),
                                                       "docetl_20": round(S.mean(x["docetl_20"] for x in v), 3)}
                                         for (c, k), v in sorted(grp.items())}
    # score against the accuracy of the weakest column in each role, within collections (rank correlation)
    from quwarts.eval.exp_why import spearman
    for role in ("aggregated", "grouped by", "filtered on"):
        res = {}
        for c in CORPORA:
            xs, ys = [], []
            for qr in queries:
                if qr["corpus"] != c or not qr["roles"][role]:
                    continue
                accs = [prof(c, col).get("our_accuracy_exact") for col in qr["roles"][role]]
                accs = [a for a in accs if a is not None]
                if accs:
                    xs.append(min(accs)); ys.append(qr["ours_20"])
            if len(xs) >= 8 and len(set(xs)) > 2:
                res[c] = {"queries": len(xs), "rank_correlation": round(spearman(xs, ys), 3)}
        out["by_role_accuracy"][role] = res
    for c in ("player", "med"):
        for nj in (0, 1, 2):
            sel = [q for q in queries if q["corpus"] == c and min(q["joins"], 2) == nj]
            if sel:
                keyacc = [prof(c, col).get("our_accuracy_exact") for q in sel for col in q["roles"]["join key"]]
                keyacc = [a for a in keyacc if a is not None]
                out["joins"][f"{c} | {nj}{'+' if nj == 2 else ''} joins"] = {
                    "queries": len(sel), "ours_20": round(S.mean(q["ours_20"] for q in sel), 3),
                    "ours_structure": round(S.mean(q["ours_structure"] for q in sel), 3),
                    "docetl_20": round(S.mean(q["docetl_20"] for q in sel), 3),
                    "docetl_structure": round(S.mean(q["docetl_structure"] for q in sel), 3),
                    "join_key_accuracy_ours": round(S.mean(keyacc), 3) if keyacc else None}
    dest = EXP / "WHY" / "profile"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps({**out, "columns": profile, "queries": queries}, indent=1, default=str))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

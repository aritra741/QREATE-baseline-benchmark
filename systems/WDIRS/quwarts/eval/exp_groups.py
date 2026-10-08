"""Why queries return too few groups, and why MIN and MAX differ (results/experiments/why/groups.json).

    python -m quwarts.eval.exp_groups

For every test query at 100% drift (unlimited on-demand extraction; served views of the replay runs):
  - each GROUP BY column: distinct non-empty values in the served table vs in the gold table;
  - the query's number of gold groups against its score;
  - for each aggregate output, over groups matched by key: share predicted above / below / within 20% of gold.
"""

from __future__ import annotations

import json
import re
import sqlite3
import statistics as S
from collections import defaultdict

import sqlglot
from sqlglot import exp

from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPO, streams, view

OUT = EXP / "why" / "groups.json"
CORPORA = ["cspaper", "player", "art", "med", "legal"]


def gold_conn(corpus: str) -> sqlite3.Connection:
    from quwarts.eval import drift_paired as P
    from quwarts.core.router.registry import get_corpus

    return P.gold_db(get_corpus(corpus))


def norm(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    return s or None


def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def main() -> dict:
    distinct_rows, group_rows, agg_rows = [], [], []
    for c in CORPORA:
        ctx = R.context(c)
        g = gold_conn(c)
        for r in streams(c)["fixed4-attribute_pool/100"]:
            q, sql = r["qid"], ctx.catalog[r["qid"]]
            v = view(c, "fixed4-attribute_pool/100", r["pos"])
            if not v.exists():
                continue
            try:
                tree = sqlglot.parse_one(sql, read="sqlite")
            except Exception:  # noqa: BLE001
                continue
            alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
            tables = set(alias.values())
            p = sqlite3.connect(v)
            # GROUP BY columns: distinct values, served vs gold
            grp = tree.find(exp.Group)
            for col in (grp.find_all(exp.Column) if grp else []):
                t = alias.get(col.table) if col.table else next(
                    (tt for tt in tables if col.name in {x[1] for x in p.execute(f'PRAGMA table_info("{tt}")')}), None)
                if not t:
                    continue
                try:
                    pd = {norm(x) for (x,) in p.execute(f'SELECT DISTINCT "{col.name}" FROM "{t}"')} - {None}
                    gd = {norm(x) for (x,) in g.execute(f'SELECT DISTINCT "{col.name}" FROM "{t}"')} - {None}
                except sqlite3.Error:
                    continue
                if gd:
                    distinct_rows.append({"corpus": c, "qid": q, "column": f"{t}.{col.name}", "pred": len(pd), "gold": len(gd),
                                          "overlap": len(pd & gd)})
            # gold groups vs score
            try:
                gold_res = g.execute(re.sub(r"/\*.*?\*/", "", sql, flags=re.S)).fetchall()
                pred_res = p.execute(re.sub(r"/\*.*?\*/", "", sql, flags=re.S)).fetchall()
            except sqlite3.Error:
                p.close()
                continue
            group_rows.append({"corpus": c, "qid": q, "gold_groups": len(gold_res), "pred_groups": len(pred_res),
                               "score": r["benchmark"]})
            # aggregate direction over matched groups
            sel = tree.find(exp.Select)
            exprs = sel.expressions if sel else []
            nk = sum(1 for e in exprs if not (e.find(exp.AggFunc)))
            kinds = []
            for e in exprs:
                a = e.find(exp.AggFunc)
                if a is not None:
                    kinds.append(a.key.upper())
            if not kinds or nk == 0:
                p.close()
                continue
            gm = {tuple(norm(x) for x in row[:nk]): row[nk:] for row in gold_res}
            for row in pred_res:
                k = tuple(norm(x) for x in row[:nk])
                if k not in gm:
                    continue
                for i, kind in enumerate(kinds):
                    if i >= len(row) - nk:
                        break
                    pv, gv = num(row[nk + i]), num(gm[k][i])
                    if pv is None or gv is None:
                        continue
                    span = max(abs(gv), 1e-9)
                    d = "within" if abs(pv - gv) <= 0.2 * span else ("above" if pv > gv else "below")
                    agg_rows.append({"corpus": c, "kind": kind, "dir": d})
            p.close()
    # summaries
    out = {}
    ratio = [r["pred"] / r["gold"] for r in distinct_rows]
    out["group_columns"] = {"columns_checked": len(distinct_rows),
                            "median_pred_over_gold_distinct": round(S.median(ratio), 3),
                            "share_fewer_distinct": round(sum(x < 1 for x in ratio) / len(ratio), 3),
                            "share_more_distinct": round(sum(x > 1 for x in ratio) / len(ratio), 3),
                            "median_overlap_share_of_gold": round(S.median(r["overlap"] / r["gold"] for r in distinct_rows), 3)}
    bins = [(1, 3), (4, 10), (11, 30), (31, 10**9)]
    out["score_by_gold_groups"] = {}
    for lo, hi in bins:
        rs = [r for r in group_rows if lo <= r["gold_groups"] <= hi]
        if rs:
            out["score_by_gold_groups"][f"{lo}-{hi if hi < 10**9 else '+'}"] = {
                "queries": len(rs), "mean_score": round(S.mean(r["score"] for r in rs), 3),
                "share_too_few_groups": round(sum(r["pred_groups"] < r["gold_groups"] for r in rs) / len(rs), 3)}
    out["aggregate_direction"] = {}
    for kind in sorted({r["kind"] for r in agg_rows}):
        rs = [r for r in agg_rows if r["kind"] == kind]
        out["aggregate_direction"][kind] = {"groups": len(rs), **{d: round(sum(r["dir"] == d for r in rs) / len(rs), 3)
                                                                  for d in ("within", "above", "below")}}
    out["per_corpus_distinct"] = {}
    for c in CORPORA:
        rr = [r["pred"] / r["gold"] for r in distinct_rows if r["corpus"] == c]
        if rr:
            out["per_corpus_distinct"][c] = {"columns": len(rr), "median_ratio": round(S.median(rr), 3)}
    OUT.write_text(json.dumps({"summary": out, "distinct": distinct_rows, "groups": group_rows}, indent=1))
    return out


def fate() -> dict:
    """Where each gold row of a GROUP BY column ends up in the last served view of the 100% stream:
    exact label, its own label in another form (one-to-one but not string-equal), merged into a label that
    mostly holds another gold group, or left empty. Adds "label_fate" and merge examples to groups.json."""
    from collections import Counter

    from quwarts.core.adapt import controller as C
    from quwarts.eval.exp_analysis import gold_by_doc, is_null

    data = json.loads(OUT.read_text())
    cols = sorted({(r["corpus"], r["column"]) for r in data["distinct"]})
    tot, per, merges, bykind = Counter(), defaultdict(Counter), defaultdict(list), defaultdict(Counter)
    for c, col in cols:
        t, a = col.split(".", 1)
        gold = gold_by_doc(c).get(t, {})
        st = streams(c)["fixed4-attribute_pool/100"]
        try:
            pv = {C._doc_name(x): y for x, y in
                  sqlite3.connect(view(c, "fixed4-attribute_pool/100", st[-1]["pos"])).execute(
                      f'SELECT doc_id,"{a}" FROM "{t}"')}
        except sqlite3.Error:
            continue
        pairs = [(norm(g[a]), norm(pv.get(doc, pv.get(doc.rsplit(".", 1)[0]))))
                 for doc, g in gold.items() if a in g and not is_null(g[a])]
        gd = {g for g, _ in pairs}
        kind = ("two-valued" if len(gd) <= 2 else
                "multi-valued" if sum("||" in g for g, _ in pairs) > 0.1 * len(pairs) else
                "numeric" if sum(num(g) is not None for g, _ in pairs) > 0.9 * len(pairs) else "categorical")
        by = defaultdict(Counter)
        for g, p in pairs:
            if p is not None:
                by[p][g] += 1
        owner = {p: cnt.most_common(1)[0][0] for p, cnt in by.items()}
        for g, p in pairs:
            k = ("empty" if p is None else "exact" if p == g else "other_form" if owner[p] == g else "merged")
            tot[k] += 1
            per[c][k] += 1
            bykind[kind][k] += 1
        for p, cnt in by.items():
            if len(cnt) > 1 and sum(cnt.values()) >= 5:
                merges[c].append({"column": col, "label": p, "gold_labels": dict(cnt.most_common(4)),
                                  "rows": sum(cnt.values())})
    share = lambda cn: {k: round(v / sum(cn.values()), 3) for k, v in cn.most_common()}  # noqa: E731
    out = {"rows": sum(tot.values()), "all": share(tot), "per_corpus": {c: share(cn) for c, cn in per.items()},
           "per_column_kind": {k: {"rows": sum(cn.values()), **share(cn)} for k, cn in bykind.items()},
           "merge_examples": {c: sorted(m, key=lambda x: -x["rows"])[:8] for c, m in merges.items()}}
    data["summary"]["label_fate"] = out
    OUT.write_text(json.dumps(data, indent=1))
    return out


if __name__ == "__main__":
    import sys

    print(json.dumps(fate() if "--fate" in sys.argv else main(), indent=1))

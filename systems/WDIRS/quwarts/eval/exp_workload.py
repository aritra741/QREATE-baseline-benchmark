"""What the workload tells a system that the documents alone do not (results/experiments/WHY/workload/summary.json).

    python -m quwarts.eval.exp_workload

Per corpus, from the build workload W0 (train), the test queries, the gold tables and the document text:
  - column usage: schema columns against the columns W0, the test queries and the whole catalogue use; concentration;
  - test structure already visible in W0: the test query's source query (it is a benchmark query with one column swapped)
    and its template (tables, joins, aggregates, group-by) against W0's;
  - the literal gap: do the constants a query compares a column with appear verbatim in the documents whose gold value
    they match? (what a system must normalize, and only the workload says to what);
  - stated or inferred: per column, the share of gold values that appear verbatim in the document and where, against
    the column's context sensitivity and accuracy (does determinacy come from the value being stated?);
  - examples: for a few columns per corpus, the sentence that states the value, or the fact that nothing does.
No model calls.
"""

from __future__ import annotations

import json
import re
import statistics as S
from collections import Counter, defaultdict
from pathlib import Path

import sqlglot
from sqlglot import exp

from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_run as R
from quwarts.eval.drift_live import fixed_design
from quwarts.eval.exp_analysis import EXP, gold_by_doc, is_null
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_transfer import kind_of, needed
from quwarts.eval.exp_why import spearman

CORPORA = ["cspaper", "player", "art", "med", "legal"]
OUT = EXP / "WHY" / "workload"


def strip_sql(sql: str) -> str:
    return re.sub(r"/\*.*?\*/", "", sql, flags=re.S)


def template(sql: str) -> dict:
    """Tables, join conditions, aggregates, group-by arity, filter columns: the shape of a query without its constants."""
    try:
        t = sqlglot.parse_one(strip_sql(sql), read="sqlite")
    except Exception:  # noqa: BLE001
        return {}
    tables = sorted({x.name for x in t.find_all(exp.Table)})
    joins = len(list(t.find_all(exp.Join)))
    aggs = sorted({a.key.upper() for a in t.find_all(exp.AggFunc)})
    grp = t.find(exp.Group)
    g = len(list(grp.find_all(exp.Column))) if grp else 0
    where = t.find(exp.Where)
    fcols = sorted({c.name for c in where.find_all(exp.Column)}) if where else []
    return {"tables": tables, "joins": joins, "aggs": aggs, "groupby": g, "filter_columns": fcols}


def constants(sql: str) -> list[tuple[str, str]]:
    """(column, constant) pairs from equality / IN predicates with string constants."""
    out = []
    try:
        t = sqlglot.parse_one(strip_sql(sql), read="sqlite")
    except Exception:  # noqa: BLE001
        return out
    for e in t.find_all(exp.EQ):
        col, lit = e.find(exp.Column), e.find(exp.Literal)
        if col is not None and lit is not None and lit.is_string:
            out.append((col.name, lit.this))
    for e in t.find_all(exp.In):
        col = e.find(exp.Column)
        if col is not None:
            for lit in e.find_all(exp.Literal):
                if lit.is_string:
                    out.append((col.name, lit.this))
    return out


def norm(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip().lower()


def num_forms(v: str) -> list[str]:
    """Ways a number may be written: 45, 45.0, 45,000."""
    try:
        f = float(v.replace(",", ""))
    except ValueError:
        return [v]
    forms = {v, f"{f:g}", f"{int(f)}" if f == int(f) else f"{f}"}
    if f == int(f) and abs(f) >= 1000:
        forms.add(f"{int(f):,}")
    return sorted(forms)


def found(text_l: str, value) -> tuple[bool, float | None]:
    """Is the value stated verbatim in the (lowercased) document; and where (relative position of the first hit)?
    Lists (`a || b`) count as stated if any item is; numbers in any common form."""
    if is_null(value):
        return False, None
    items = [x.strip() for x in str(value).split("||")] if "||" in str(value) else [str(value)]
    best = None
    for it in items:
        for form in num_forms(it):
            f = norm(form)
            if len(f) < 2:
                continue
            i = text_l.find(f)
            if i >= 0:
                pos = i / max(1, len(text_l))
                best = pos if best is None else min(best, pos)
    return best is not None, best


def main() -> dict:
    sens = json.loads((EXP / "WHY" / "context" / "summary.json").read_text())["columns"]
    out = {}
    examples = {}
    for c in CORPORA:
        ctx = R.context(c)
        design = fixed_design(c, "attribute_pool")
        gold = gold_by_doc(c)
        fields = fields_of(c)
        test = list(dict.fromkeys(design["test"]))
        w0 = dict(ctx.w0)
        schema = {f"{t}.{a}" for t, rows in gold.items() for g in rows.values() for a in g}
        # ---- column usage
        use_w0, use_test, use_all = Counter(), Counter(), Counter()
        for q, sql in w0.items():
            for col in needed(ctx, q) & schema:
                use_w0[col] += 1
        for q in test:
            for col in needed(ctx, q) & schema:
                use_test[col] += 1
        for q in ctx.catalog:
            for col in needed(ctx, q) & schema:
                use_all[col] += 1
        tot = sum(use_w0.values())
        top = [n for _, n in use_w0.most_common()]
        conc = {k: round(sum(top[:k]) / tot, 3) for k in (3, 5, 10) if tot}
        usage = {"schema_columns": len(schema), "w0_queries": len(w0), "test_queries": len(test),
                 "columns_used_by_w0": len(use_w0), "columns_used_by_test": len(use_test),
                 "columns_used_by_any_query": len(use_all),
                 "test_columns_not_in_w0": sorted(set(use_test) - set(use_w0)),
                 "share_of_w0_uses_in_top_k_columns": conc,
                 "w0_group_by_columns": sorted({col.name for q, sql in w0.items() for col in (
                     (sqlglot.parse_one(strip_sql(sql), read="sqlite").find(exp.Group) or exp.Group()).find_all(exp.Column))}),
                 "w0_filter_columns": sorted({x for q, sql in w0.items() for x in template(sql).get("filter_columns", [])})}
        # ---- test structure visible in W0
        w0_templates = {json.dumps(template(sql), sort_keys=True) for sql in w0.values()}
        w0_shapes = {json.dumps({k: v for k, v in template(sql).items() if k != "filter_columns"}, sort_keys=True) for sql in w0.values()}
        src_in_w0 = tmpl_in_w0 = shape_in_w0 = 0
        for q in test:
            m = re.match(r"attr:(.+):[0-9a-f]{8}$", q)
            src = m.group(1) if m else None
            src_in_w0 += src in w0
            tp = template(ctx.catalog[q])
            tmpl_in_w0 += json.dumps(tp, sort_keys=True) in w0_templates
            shape_in_w0 += json.dumps({k: v for k, v in tp.items() if k != "filter_columns"}, sort_keys=True) in w0_shapes
        structure = {"test_queries": len(test), "source_query_in_w0": src_in_w0,
                     "same_template_as_a_w0_query": tmpl_in_w0,
                     "same_shape_as_a_w0_query (tables, joins, aggregates, group-by arity)": shape_in_w0}
        # ---- the literal gap: constants against documents
        texts: dict[tuple, str] = {}

        def text(t: str, d: str) -> str:
            if (t, d) not in texts:
                p = ctx.docs.get(t, {}).get(d)
                texts[(t, d)] = read_document(Path(p)).lower() if p else ""
            return texts[(t, d)]

        def gold_rows_with(t: str, a: str, const: str):
            for d, g in gold.get(t, {}).items():
                if a in g and not is_null(g[a]) and norm(const) in {norm(x) for x in str(g[a]).split("||")}:
                    yield d

        gap_rows = []
        seen = set()
        for src_name, qs in (("w0", w0.items()), ("test", [(q, ctx.catalog[q]) for q in test])):
            for q, sql in qs:
                tp = template(sql)
                for col, const in constants(sql):
                    t = next((tt for tt in tp.get("tables", []) if f"{tt}.{col}" in schema), None)
                    if t is None or (t, col, const) in seen:
                        continue
                    seen.add((t, col, const))
                    docs = list(gold_rows_with(t, col, const))
                    if not docs:
                        continue
                    hits = sum(norm(const) in text(t, d) for d in docs)
                    gap_rows.append({"query_set": src_name, "column": f"{t}.{col}", "constant": const, "gold_rows": len(docs),
                                     "verbatim_share": round(hits / len(docs), 3), "kind": kind_of(fields[f"{t}.{col}"]) if f"{t}.{col}" in fields else "?"})
        gap = {"constants": len(gap_rows),
               "mean_verbatim_share": round(S.mean(r["verbatim_share"] for r in gap_rows), 3) if gap_rows else None,
               "constants_never_verbatim": sum(r["verbatim_share"] == 0 for r in gap_rows),
               "constants_always_verbatim": sum(r["verbatim_share"] == 1 for r in gap_rows),
               "by_kind": {k: round(S.mean(r["verbatim_share"] for r in gap_rows if r["kind"] == k), 3)
                           for k in ("number", "yes/no", "category", "list", "free text") if any(r["kind"] == k for r in gap_rows)},
               "rows": gap_rows}
        # ---- stated or inferred, per column
        by_col = {r["column"]: r for r in sens.get(f"qwen7b/{c}", [])}
        stated_rows = []
        ex = defaultdict(list)
        for col in sorted(schema):
            t, a = col.split(".", 1)
            if col not in fields or t not in ctx.docs:
                continue
            vals = [(d, g[a]) for d, g in gold.get(t, {}).items() if a in g and not is_null(g[a]) and d in ctx.docs[t]]
            if len(vals) < 10:
                continue
            hits, poss = 0, []
            for d, v in vals:
                ok, pos = found(text(t, d), v)
                hits += ok
                if ok:
                    poss.append(pos)
                if len(ex[col]) < 3 and (ok or len(ex[col]) < 1):
                    tl = text(t, d)
                    snippet = ""
                    if ok:
                        it = norm([x for x in str(v).split("||")][0])
                        i = tl.find(it)
                        if i < 0:
                            for form in num_forms(str(v).split("||")[0].strip()):
                                i = tl.find(norm(form))
                                if i >= 0:
                                    break
                        snippet = tl[max(0, i - 120): i + 120].replace("\n", " ") if i >= 0 else ""
                    ex[col].append({"doc": d, "gold": str(v)[:80], "stated": ok, "snippet": snippet})
            e = {"corpus": c, "column": col, "kind": kind_of(fields[col]), "gold_values": len(vals),
                 "stated_share": round(hits / len(vals), 3),
                 "median_position": round(S.median(poss), 3) if poss else None,
                 "in_w0": col in use_w0, "in_test": col in use_test,
                 "sensitivity_7b": by_col.get(col, {}).get("sensitivity"), "accuracy_7b": by_col.get(col, {}).get("accuracy")}
            stated_rows.append(e)
        ss = [r for r in stated_rows if r["sensitivity_7b"] is not None]
        stated = {"columns": len(stated_rows),
                  "mean_stated_share": round(S.mean(r["stated_share"] for r in stated_rows), 3),
                  "by_kind": {k: {"columns": len(rs), "stated_share": round(S.mean(r["stated_share"] for r in rs), 3),
                                  "median_position": round(S.median([r["median_position"] for r in rs if r["median_position"] is not None]), 3)
                                  if any(r["median_position"] is not None for r in rs) else None}
                              for k in ("number", "yes/no", "category", "list", "free text")
                              if (rs := [r for r in stated_rows if r["kind"] == k])},
                  "spearman_stated_vs_sensitivity": round(spearman([r["stated_share"] for r in ss], [r["sensitivity_7b"] for r in ss]), 3) if len(ss) > 4 else None,
                  "spearman_stated_vs_accuracy": round(spearman([r["stated_share"] for r in ss if r["accuracy_7b"] is not None],
                                                                [r["accuracy_7b"] for r in ss if r["accuracy_7b"] is not None]), 3) if len(ss) > 4 else None,
                  "columns_with_sensitivity": len(ss), "rows": stated_rows}
        examples[c] = {col: v for col, v in ex.items() if col in use_test or col in use_w0}
        out[c] = {"usage": usage, "structure": structure, "literal_gap": gap, "stated_or_inferred": stated}
    # pooled: stated share vs sensitivity over all corpora
    allr = [r for c in out for r in out[c]["stated_or_inferred"]["rows"] if r["sensitivity_7b"] is not None]
    pooled = {"columns": len(allr),
              "spearman_stated_vs_sensitivity": round(spearman([r["stated_share"] for r in allr], [r["sensitivity_7b"] for r in allr]), 3),
              "spearman_stated_vs_accuracy": round(spearman([r["stated_share"] for r in allr if r["accuracy_7b"] is not None],
                                                            [r["accuracy_7b"] for r in allr if r["accuracy_7b"] is not None]), 3),
              "by_kind": {k: {"columns": len(rs), "stated_share": round(S.mean(r["stated_share"] for r in rs), 3),
                              "sensitivity": round(S.mean(r["sensitivity_7b"] for r in rs), 3)}
                          for k in ("number", "yes/no", "category", "list", "free text") if (rs := [r for r in allr if r["kind"] == k])}}
    for lo, hi in ((0, 0.34), (0.34, 0.67), (0.67, 1.01)):
        rs = [r for r in allr if lo <= r["stated_share"] < hi]
        if rs:
            pooled[f"stated_{lo:.2f}-{min(hi, 1):.2f}"] = {"columns": len(rs), "mean_sensitivity": round(S.mean(r["sensitivity_7b"] for r in rs), 3),
                                                          "mean_accuracy": round(S.mean(r["accuracy_7b"] for r in rs if r["accuracy_7b"] is not None), 3)}
    out["pooled"] = pooled
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    (OUT / "examples.json").write_text(json.dumps(examples, indent=1, default=str))
    return out


if __name__ == "__main__":
    o = main()
    for c in CORPORA:
        v = o[c]
        print("==", c)
        print(" usage:", {k: x for k, x in v["usage"].items() if k not in ("w0_group_by_columns", "w0_filter_columns")})
        print(" structure:", v["structure"])
        print(" literal gap:", {k: x for k, x in v["literal_gap"].items() if k != "rows"})
        print(" stated:", {k: x for k, x in v["stated_or_inferred"].items() if k != "rows"})
    print("== pooled:", o["pooled"])

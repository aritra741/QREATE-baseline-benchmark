"""Template-paired drift streams (results/drift_paired). AUDIT: gold validates generated queries.

Every level of a stream is built from the same base queries (the in-distribution test queries T0 of
``drift_design``; W0 and the build reads are unchanged). At drift level p, p% of the base queries are
replaced by drifted versions of themselves, so only drift changes between levels, and each drifted query
is paired with its own source.

* value drift (parameter drift, as in DSB's shifting parameter distributions): the query's constants are
  replaced by constants no build query uses, selectivity-matched (``drift_design.value_variants``; Bruno,
  Chaudhuri & Thomas generate parameters for target cardinalities)
* attribute drift (unseen columns on the same template, as in Negi et al.'s out-of-distribution
  workloads): one column of the query is replaced by a schema column the build never read, with the same
  role and type and a similar number of distinct values (within a factor of two); string constants compared
  with it become selectivity-matched values of the new column. Columns used in joins, LIKE patterns, range
  comparisons or CASE conditions are not swapped. A column under AVG/SUM/MIN/MAX is replaced only by a column
  whose gold values are numbers (at least 90% of its non-empty values parse as numbers, so a year stored as text
  qualifies and a name, a list or a free-text label does not): the alphabetical extreme of a text column is not a
  question anyone asks.
* combined: drifted positions alternate between the two (a base query with one kind of variant uses it).
Levels 0/25/50/75/100 of N = 28 base queries (fewer when fewer base queries have a variant), gradual
streams of 2N (every base query twice, drift probability rising 0 -> 1), 3 seeds; each generated query
must return a non-empty answer on gold.

    python -m quwarts.eval.drift_paired --corpus art          # write results/drift_paired/art/design_seed*.json
    QUWARTS_DRIFT_DESIGN=drift_paired python -m quwarts.eval.drift_run --corpus art --raw / --replay
    python -m quwarts.eval.drift_paired --report              # paired differences (needs the replay)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
import sys
from collections import Counter
from typing import Any

from quwarts.core.router.registry import RESULTS
from quwarts.eval import drift_design as DD

SRC = RESULTS / "drift_design"
ROOT = RESULTS / "drift_paired"
SEEDS = (0, 1, 2)
N = 28
LEVELS = (0, 25, 50, 75, 100)
AXES = ("attribute", "value", "combined")
VARIANTS = 3


def gold_db(spec):
    from diagnostics.run_config_grid import load_ground_truth
    from spp.config_grid import _build_in_memory_db
    from quwarts.eval.router_execute_v3 import DATASET
    from quwarts.experiments.synthesize_case80 import gold_name

    return _build_in_memory_db(load_ground_truth(gold_name(DATASET[spec.name])))


def column_swaps(corpus: str, t0: list[dict], w0_attrs: set[tuple[str, str]], catalog_sql: dict[str, str]) -> dict[str, list[dict]]:
    """Up to ``VARIANTS`` column-swapped versions of each base query, validated on gold."""

    import sqlglot
    from sqlglot import exp

    from quwarts.core.router.registry import get_corpus
    from quwarts.core.router.workload_features import alias_map, resolve_column, table_attribute_names

    spec = get_corpus(corpus)
    gold = gold_db(spec)
    values = DD.column_values(corpus)
    schema = spec.benchmark_attribute_descriptions(purpose="protocol")
    kinds: dict[tuple[str, str], str] = {}
    distinct: dict[tuple[str, str], int] = {}
    for tb in spec.tables:
        for a, info in schema.get(tb.attributes_key, {}).items():
            vt = (info.get("value_type") or info.get("type") or "str") if isinstance(info, dict) else "str"
            kinds[(tb.sql_name, a)] = "num" if vt in ("int", "float") else "text"
            try:
                distinct[(tb.sql_name, a)] = gold.execute(f'SELECT COUNT(DISTINCT "{a}") FROM "{tb.sql_name}"').fetchone()[0]
            except sqlite3.Error:
                distinct[(tb.sql_name, a)] = 0
    targets = {k for k in kinds if k not in w0_attrs and distinct.get(k, 0) > 0}

    def numeric_valued(k: tuple[str, str]) -> bool:
        try:
            vals = [v for (v,) in gold.execute(f'SELECT "{k[1]}" FROM "{k[0]}"') if v is not None and str(v).strip() != ""]
        except sqlite3.Error:
            return False
        ok = 0
        for v in vals:
            try:
                float(str(v).replace(",", "").replace("$", "").strip())
                ok += 1
            except ValueError:
                pass
        return bool(vals) and ok >= 0.9 * len(vals)

    numeric = {k: numeric_valued(k) for k in kinds}
    table_attrs = table_attribute_names(spec, catalog_sql)
    known = {s.strip() for s in catalog_sql.values()}
    out: dict[str, list[dict]] = {}
    for r in t0:
        tree = sqlglot.parse_one(r["sql"], read="sqlite")
        aliases = alias_map(tree)
        occ: dict[tuple[str, str], list] = {}
        for col in tree.find_all(exp.Column):
            t = resolve_column(col, aliases, table_attrs)
            if t is not None:
                occ.setdefault((t, col.name), []).append(col)
        rng = random.Random(f"swap:{corpus}:{r['id']}")
        made, tried = [], set()
        sources = [k for k in sorted(occ) if k in kinds]
        rng.shuffle(sources)
        for src in sources:
            roles, blocked, eq_nodes = set(), False, []
            for col in occ[src]:
                anc = col.parent
                while anc is not None and not isinstance(anc, exp.Select):
                    if isinstance(anc, (exp.Like, exp.ILike, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between, exp.If, exp.Case)) \
                            or (isinstance(anc, exp.Join)):
                        blocked = True
                    if isinstance(anc, (exp.EQ, exp.NEQ, exp.In)):
                        lits = [x for x in anc.find_all(exp.Literal)]
                        if any(not x.is_string for x in lits):
                            blocked = True
                        eq_nodes.append(anc)
                        roles.add("filter")
                    if isinstance(anc, (exp.Avg, exp.Sum, exp.Min, exp.Max)):
                        roles.add("numagg")
                    if isinstance(anc, exp.Group):
                        roles.add("group")
                    anc = anc.parent
                if col.find_ancestor(exp.Join) is not None:
                    blocked = True
            if blocked:
                continue
            cands = [k for k in sorted(targets) if k[0] == src[0] and kinds[k] == kinds[src]]
            if "numagg" in roles:  # an aggregated column becomes another column of numbers
                cands = [k for k in cands if numeric[k]]
            if roles & {"group", "filter"}:
                d0 = max(1, distinct.get(src, 1))
                cands = [k for k in cands if 0.5 <= max(1, distinct[k]) / d0 <= 2]
            rng.shuffle(cands)
            for tgt in cands:
                if len(made) >= VARIANTS or (src, tgt) in tried:
                    break
                tried.add((src, tgt))
                t = tree.copy()
                aliases_t = alias_map(t)
                ok = True
                for col in list(t.find_all(exp.Column)):
                    if resolve_column(col, aliases_t, table_attrs) == src[0] and col.name == src[1]:
                        col.set("this", exp.to_identifier(tgt[1]))
                pool_vals = [(v, n) for v, n in values.get(f"{tgt[0]}.{tgt[1]}".lower(), Counter()).items()]
                for node in t.find_all(exp.EQ, exp.NEQ, exp.In):
                    cols = [c for c in node.find_all(exp.Column) if c.name == tgt[1]]
                    if not cols:
                        continue
                    used: set[str] = set()
                    for lit in [x for x in node.find_all(exp.Literal) if x.is_string and x.this != ""]:
                        cand = [(v, n) for v, n in pool_vals if v not in used]
                        if not cand:
                            ok = False
                            break
                        old_n = values.get(f"{src[0]}.{src[1]}".lower(), Counter()).get(lit.this, 0)
                        v = DD.matched(rng, cand, old_n)
                        used.add(v)
                        lit.replace(exp.Literal.string(v))
                if not ok:
                    continue
                # Every aggregated column of the variant must hold numbers, whichever column was swapped (a base query
                # that takes MIN/MAX of a text column yields no variant).
                aggd = {resolve_column(c, aliases_t, table_attrs) and (resolve_column(c, aliases_t, table_attrs), c.name)
                        for f in t.find_all(exp.Avg, exp.Sum, exp.Min, exp.Max) for c in f.find_all(exp.Column)}
                if any(k and k in numeric and not numeric[k] for k in aggd):
                    continue
                sql = t.sql(dialect="sqlite")
                if sql.strip() in known:
                    continue
                try:
                    got = gold.execute(sql).fetchall()
                except sqlite3.Error:
                    continue
                if not any(any(v is not None and str(v).strip() != "" for v in row) for row in got):
                    continue
                dig = hashlib.sha256(sql.encode()).hexdigest()[:8]
                made.append({"id": f"attr:{r['id']}:{dig}", "sql": sql, "derived_from": r["id"],
                             "swap": [f"{src[0]}.{src[1]}", f"{tgt[0]}.{tgt[1]}"], "sources": [f"attribute-drift:{r['id']}"]})
                known.add(sql.strip())
            if len(made) >= VARIANTS:
                break
        if made:
            out[r["id"]] = made
    return out


def record(corpus: str, spec, v: dict, context: dict[str, str], table_attrs) -> dict:
    from quwarts.core.adapt import controller as C
    from quwarts.core.adapt import drift as D

    return {"sql": v["sql"], "sources": v["sources"], "derived_from": v["derived_from"], "swap": v.get("swap"),
            "attributes": {t: sorted(a) for t, a in C.query_attributes(spec, v["id"], v["sql"], context).items()},
            "features": sorted(D.representation(v["sql"])), "template": D.template(v["sql"]),
            "literals": DD.literals_of(v["sql"], table_attrs)}


def design(corpus: str) -> dict[str, Any]:
    from quwarts.core.router.registry import get_corpus
    from quwarts.core.router.workload_features import table_attribute_names

    spec = get_corpus(corpus)
    src = json.loads((SRC / corpus / "design_seed0.json").read_text())
    cat = src["queries"]
    w0 = list(json.loads((SRC / corpus / "build.json").read_text())["build"])
    t0 = src["in_distribution"]
    rows = lambda ids: [{"id": q, **cat[q]} for q in ids]  # noqa: E731
    w0_attrs = {(t, a) for q in w0 for t, attrs in cat[q]["attributes"].items() for a in attrs}
    catalog_sql = {q: r["sql"] for q, r in cat.items()}
    table_attrs = table_attribute_names(spec, catalog_sql)
    swaps = column_swaps(corpus, rows(t0), w0_attrs, catalog_sql)
    vals: dict[str, list[dict]] = {}
    for v in DD.value_variants(corpus, rows(t0), rows(w0), DD.BUILD_SEED):
        vals.setdefault(v["derived_from"], []).append(v)
    context = dict(catalog_sql)
    for vs in list(swaps.values()) + list(vals.values()):
        for v in vs:
            context[v["id"]] = v["sql"]
    variants = {"attribute": swaps, "value": vals}
    queries = {q: cat[q] for q in w0 + t0}
    for kind in variants.values():
        for vs in kind.values():
            for v in vs:
                queries[v["id"]] = record(corpus, spec, v, context, table_attrs)
    build_rows = [{"id": q, **cat[q]} for q in w0]
    ROOT.joinpath(corpus).mkdir(parents=True, exist_ok=True)
    summary = {"corpus": corpus, "base_queries": len(t0),
               "with_attribute_variant": len(swaps), "with_value_variant": len(vals),
               "with_both": len(set(swaps) & set(vals)), "seeds": {}}
    for seed in SEEDS:
        streams, pairs, stats = {}, {}, {}
        for axis in AXES:
            base = sorted(set(swaps) | set(vals)) if axis == "combined" else sorted(variants[axis])
            rng = random.Random(f"{seed}:{axis}")
            rng.shuffle(base)
            base = base[:N]
            n = len(base)
            order = list(range(n))
            rng.shuffle(order)
            def kind(i, pos):  # combined: alternate the two kinds; a query with one kind of variant uses it
                if axis != "combined":
                    return axis
                want = "attribute" if i % 2 == 0 else "value"
                return want if base[pos] in variants[want] else ("value" if want == "attribute" else "attribute")
            kind_of = {pos: kind(i, pos) for i, pos in enumerate(order)}
            def variant(q, k, j):
                vs = variants[k][q]
                return vs[(seed + j) % len(vs)]["id"]
            for p in LEVELS:
                k = round(n * p / 100)
                drifted = set(order[:k])
                stream = [variant(base[i], kind_of[i], 0) if i in drifted else base[i] for i in range(n)]
                perm = list(range(n))
                random.Random(seed * 100 + p).shuffle(perm)
                streams[f"{axis}/{p}"] = [stream[i] for i in perm]
                pairs[f"{axis}/{p}"] = {stream[i]: base[i] for i in range(n)}
                stats[f"{axis}/{p}"] = DD.characterize(build_rows, [{"id": q, **queries[q]} for q in stream])
            g_rng = random.Random(seed * 7 + 3)
            gradual, gpairs = [], {}
            for i in range(2 * n):
                b = base[i % n]
                if g_rng.random() < i / max(1, 2 * n - 1):
                    q = variant(b, kind_of[i % n], i // n)
                else:
                    q = b
                gradual.append(q)
                gpairs[q] = b
            streams[f"{axis}/gradual"] = gradual
            pairs[f"{axis}/gradual"] = gpairs
            stats[f"{axis}/gradual"] = DD.characterize(build_rows, [{"id": q, **queries[q]} for q in gradual])
            summary["seeds"].setdefault(seed, {})[axis] = n
        payload = {"corpus": corpus, "seed": seed, "focus": src["focus"], "build": w0, "in_distribution": t0,
                   "attribute_pool": sorted(v["id"] for vs in swaps.values() for v in vs),
                   "value_pool": sorted(v["id"] for vs in vals.values() for v in vs),
                   "streams": streams, "pairs": pairs, "characterization": stats, "queries": queries}
        (ROOT / corpus / f"design_seed{seed}.json").write_text(json.dumps(payload, indent=1))
    (ROOT / corpus / "design_summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def paired_report() -> str:
    """Per corpus, axis and level: mean score of the drifted queries and of their own sources on the same
    stream family (the 0% stream), for QuWARTS and the static build; benchmark metric."""

    import os

    os.environ["QUWARTS_DRIFT_DESIGN"] = "drift_paired"
    from quwarts.eval import drift_run as R
    from quwarts.eval.represent_eval import paired_ci

    lines = ["# Template-paired drift (results/drift_paired)", "",
             "Each drifted query is compared with its own source query, answered in the 0% stream of the same seed. Benchmark metric, mean over 3 seeds.", "",
             "| Corpus | Axis | Level | drifted queries | QuWARTS: source / drifted | QuWARTS drifted - source [95% CI] | static: source / drifted |",
             "|---|---|---|---:|---|---|---|"]
    for c in R.CORPORA:
        try:
            res = R.results(c)
        except FileNotFoundError:
            continue
        if not res:
            continue
        for axis in AXES:
            for p in (25, 50, 75, 100):
                dq, ds, sq, ss = [], [], [], []
                for s in SEEDS:
                    key, base_key = (s, f"{axis}/{p}"), (s, f"{axis}/0")
                    if key not in res or base_key not in res:
                        continue
                    design = json.loads((ROOT / c / f"design_seed{s}.json").read_text())
                    st, st0 = design["streams"][f"{axis}/{p}"], design["streams"][f"{axis}/0"]
                    pos0 = {q: i for i, q in enumerate(st0)}
                    pairs = design["pairs"][f"{axis}/{p}"]
                    for i, q in enumerate(st):
                        b = pairs[q]
                        if q == b:
                            continue
                        j = pos0[b]
                        dq.append(res[key]["acc"]["quwarts"]["benchmark"][i]); sq.append(res[base_key]["acc"]["quwarts"]["benchmark"][j])
                        ds.append(res[key]["acc"]["static"]["benchmark"][i]); ss.append(res[base_key]["acc"]["static"]["benchmark"][j])
                if not dq:
                    continue
                m = lambda x: sum(x) / len(x)  # noqa: E731
                diff = [a - b for a, b in zip(dq, sq)]
                ci = paired_ci(diff) if len(diff) > 2 else [float("nan")] * 2
                lines.append(f"| {c} | {axis} | {p}% | {len(dq)} | {m(sq):.3f} / {m(dq):.3f} | {m(diff):+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}] | {m(ss):.3f} / {m(ds):.3f} |")
    text = "\n".join(lines)
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "PAIRED.md").write_text(text + "\n")
    return text


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", choices=DD.CORPORA)
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    if a.corpus:
        print(json.dumps(design(a.corpus)))
    if a.report:
        print(paired_report())
    return 0


if __name__ == "__main__":
    sys.exit(main())

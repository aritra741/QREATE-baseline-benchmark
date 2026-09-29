"""Drift experiment design: build workloads and drifting query streams for every corpus (AUDIT: gold is
used only to validate queries and to draw constants, as a query generator does; the system under test
never sees it).

    python -m quwarts.eval.drift_design --corpus art      # build workloads, streams, characterization
    python -m quwarts.eval.drift_design --report

Workload model. A query is described by the attributes it reads, its CliffGuard (column, clause)
features (Mozafari et al., SIGMOD 2015) and its string constants. A workload is a distribution over
queries; drift is a change of that distribution (CliffGuard's distance; QB5000's templates, Ma et al.,
SIGMOD 2018; the drift types of Negi et al., VLDB 2023). Three axes are varied separately, because each
asks something different of the system:

* **attribute drift**: queries read attributes the build workload never read (new extraction: patch or
  rebuild)
* **value drift**: the build workload's query shapes with string constants it never used (the stored
  values must be written the way the new constants are: representation)
* **combined**: half of the drifted queries from each

Pool (``drift_pool``): every scorable query we have that executes on gold with a non-empty answer, from
the benchmark's query files and the analytical case80 workloads.

Build workload. Attributes are ordered by the Fiedler vector of their co-occurrence graph (two
attributes are linked by the number of pool queries that read both; spectral bisection keeps attributes
that are queried together on the same side), and cut where the queries reading only the first side and
the rest are most balanced. The first side is the build workload's attribute focus A0. Queries within A0
are split once (seed 0), 60/40, into the build workload W0 and the in-distribution test queries T0: the
build's extraction is a real read whose prompts are informed by W0 alone, so there is one W0 per corpus. Queries
reading any attribute outside A0 form the attribute-drift pool. For value drift, each query of W0 and T0
with constants is re-instantiated (``value_variants``): equality constants (``=``, ``!=``, ``IN``) by gold
values of the same column that no W0 query uses, and one ``LIKE '%core%'`` pattern by a word of the
column's gold values that no W0 pattern uses (with its ``CASE`` label, a new value family), drawn by
frequency; a variant is kept if its gold answer is non-empty and it is not already a pool query.

Streams. For each axis and drift level p in {0, 25, 50, 75, 100}%: N = 28 queries, a share p from the
axis's drift pool and the rest from T0; levels are nested (the drifted queries of a level contain those of
the lower levels) and shuffled with the seed. Three seeds per corpus. A gradual stream (2N queries, the
drift probability rising linearly from 0 to 1) per axis and seed serves the adaptive controller. The
three seeds vary which drifted and in-distribution queries a stream draws and their order.

Characterization, per stream against W0: share of queries reading an attribute W0 does not read, with a
(column, clause) feature W0 does not have, with an operator profile (join, group, having, case, in, like,
comparisons, aggregates, ...) W0 does not have, with a string constant (on its column) W0 does not use; new attributes per query; the
share of the stream's feature occurrences W0 never has; the Jensen-Shannon divergence between the two
feature distributions; CliffGuard's delta. (QB5000 templates keep column names and are nearly unique
per query in these pools, so their novelty is reported but not informative.)
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import random
import sys
from collections import Counter
from typing import Any

from quwarts.core.router.registry import RESULTS

CORPORA = ["med", "finan", "legal", "art", "cspaper", "player"]
ROOT = RESULTS / "drift_design"
SEEDS = (0, 1, 2)
N = 28
LEVELS = (0, 25, 50, 75, 100)
AXES = ("attribute", "value", "combined")
BUILD_SHARE = 0.6
BUILD_SEED = 0


def attrs_of(row: dict) -> frozenset[str]:
    return frozenset(f"{t}.{a}" for t, attrs in row["attributes"].items() for a in attrs)


def usable(corpus: str) -> list[dict]:
    rows = json.loads((ROOT / corpus / "pool.json").read_text())
    return [r for r in rows if r["valid"] and r["scorable"]]


def bisect(queries: list[frozenset[str]]) -> dict[str, Any]:
    """Spectral bisection of the attribute co-occurrence graph, cut at the balance point."""

    import numpy as np

    attrs = sorted(set().union(*queries))
    index = {a: i for i, a in enumerate(attrs)}
    w = np.zeros((len(attrs), len(attrs)))
    for q in queries:
        for a, b in itertools.combinations(sorted(q), 2):
            w[index[a], index[b]] += 1
            w[index[b], index[a]] += 1
    lap = np.diag(w.sum(1)) - w
    _vals, vecs = np.linalg.eigh(lap)
    fiedler = vecs[:, 1]
    best = None
    for sign in (1, -1):
        order = [attrs[i] for i in np.argsort(sign * fiedler, kind="stable")]
        for k in range(1, len(attrs)):
            side = set(order[:k])
            inside = sum(q <= side for q in queries)
            balance = min(inside, len(queries) - inside)
            if best is None or balance > best["balance"]:
                best = {"balance": balance, "focus": sorted(side), "order": order, "k": k, "inside": inside}
    cut = sum(w[index[a], index[b]] for a in best["focus"] for b in attrs if b not in best["focus"])
    best["cut_share"] = round(float(cut / max(1.0, w.sum() / 2)), 3)
    return best


def column_values(corpus: str) -> dict[str, Counter]:
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.core.router.registry import get_corpus
    from quwarts.eval.router_execute_v3 import DATASET
    from quwarts.experiments.synthesize_case80 import gold_name

    out: dict[str, Counter] = {}
    for table, rows in load_ground_truth(gold_name(DATASET[get_corpus(corpus).name])).items():
        for r in rows:
            for k, v in r.items():
                if isinstance(v, str) and v.strip() and v.strip().lower() not in ("null", "none", "nan"):
                    out.setdefault(f"{table}.{k}".lower(), Counter())[v] += 1
    return out


def string_constants(sql: str, spec, context: dict[str, str]):
    """(literal node, 'table.column') for string constants in =, != and IN comparisons with one column."""

    import sqlglot
    from sqlglot import exp

    from quwarts.core.router.workload_features import alias_map, resolve_column, table_attribute_names

    tree = sqlglot.parse_one(sql, read="sqlite")
    aliases = alias_map(tree)
    table_attrs = table_attribute_names(spec, context)
    found = []
    for node in tree.find_all(exp.EQ, exp.NEQ, exp.In):
        cols = list(node.find_all(exp.Column))
        if len(cols) != 1:
            continue
        table = resolve_column(cols[0], aliases, table_attrs)
        if table is None:
            continue
        lits = [x for x in (node.expressions if isinstance(node, exp.In) else [node.left, node.right])
                if isinstance(x, exp.Literal) and x.is_string and x.this != ""]
        for lit in lits:
            found.append((lit, f"{table}.{cols[0].name}".lower()))
    return tree, found


VARIANTS_PER_QUERY = 3


def sites(tree, table_attrs: dict[str, set[str]]):
    """Constant sites of a parsed query: equality ones (literal, column) in ``=``, ``!=`` and ``IN`` with one
    column, and pattern ones (literal, column, core) in ``LIKE`` with a ``%core%``-style pattern."""

    import re

    from sqlglot import exp

    from quwarts.core.router.workload_features import alias_map, resolve_column

    aliases = alias_map(tree)
    eq, like = [], []
    for node in tree.find_all(exp.EQ, exp.NEQ, exp.In):
        cols = list(node.find_all(exp.Column))
        if len(cols) != 1:
            continue
        table = resolve_column(cols[0], aliases, table_attrs)
        if table is None:
            continue
        items = node.expressions if isinstance(node, exp.In) else [node.left, node.right]
        for lit in items:
            if isinstance(lit, exp.Literal) and lit.is_string and lit.this != "":
                eq.append((lit, f"{table}.{cols[0].name}".lower(), node))
    for node in tree.find_all(exp.Like, exp.ILike):
        cols = list(node.this.find_all(exp.Column)) if node.this is not None else []
        lit = node.expression
        if len(cols) != 1 or not (isinstance(lit, exp.Literal) and lit.is_string):
            continue
        table = resolve_column(cols[0], aliases, table_attrs)
        core = lit.this.strip("%_")
        if table is None or not core or "%" in core or "_" in core or not re.search(r"[A-Za-z]", core):
            continue
        like.append((lit, f"{table}.{cols[0].name}".lower(), core))
    return eq, like


def column_tokens(values: dict[str, Counter]) -> dict[str, Counter]:
    """Words of each column's gold values that can name a value family: 3+ letters, in at least 2 cells
    and at most 30% of them (a word in most cells, like ``LLP`` among auditors, names no family), keyed
    by their commonest spelling."""

    import re

    out: dict[str, Counter] = {}
    for col, counts in values.items():
        cells = sum(counts.values())
        folded: Counter = Counter()
        spelling: dict[str, Counter] = {}
        for v, n in counts.items():
            for w in set(re.findall(r"[A-Za-z][A-Za-z&.'-]{2,}", v)):
                folded[w.casefold()] += n
                spelling.setdefault(w.casefold(), Counter())[w] += n
        out[col] = Counter({spelling[k].most_common(1)[0][0]: n for k, n in folded.items() if 2 <= n <= 0.3 * cells})
    return out


def matched(rng: random.Random, pool: list[tuple[str, int]], target: int) -> str:
    """A candidate drawn uniformly among those whose gold count is within a factor of two of ``target``
    (the replaced constant's count); the nearest candidates in log count when none is."""

    import math

    target = max(1, target)
    dist = [(abs(math.log(max(1, n) / target)), v) for v, n in pool]
    band = sorted(v for d, v in dist if d <= math.log(2))
    if not band:
        best = min(d for d, _v in dist)
        band = sorted(v for d, v in dist if d <= best + 1e-9)
    return band[rng.randrange(len(band))]


def cells_with(counts: Counter, core: str) -> int:
    """Gold cells of a column whose value contains ``core`` (case-folded)."""

    c = core.casefold()
    return sum(n for v, n in counts.items() if c in v.casefold())


def value_variants(corpus: str, rows: list[dict], build: list[dict], seed: int) -> list[dict]:
    """Re-instantiate queries with constants that no build query uses (validated on gold), up to
    ``VARIANTS_PER_QUERY`` per source query, returned round-robin over sources (first variants of every
    source, then second variants), so a stream draws from as many sources as possible.

    * equality constants (``=``, ``!=``, ``IN``): every one is replaced by a gold value of its column that no
      build query compares it with (distinct within an ``IN`` list)
    * pattern constants (``LIKE '%core%'``): one site per variant gets a new core, a word of the column's
      gold values that no build query's pattern uses; when the pattern selects a ``CASE`` branch whose label
      is the old core, the label becomes the new core (a new value family, as an analyst adds one)

    Replacements are selectivity-matched: drawn uniformly among the candidates that occur in about as many
    gold cells as the replaced constant (within a factor of two; the nearest ones when none is), so a
    variant changes the constant, not how many rows it selects. (Drawing by frequency favoured common
    values, which select more rows and are extracted correctly more often, and made value drift easier.)
    """

    import sqlite3

    from diagnostics.run_config_grid import load_ground_truth
    from spp.config_grid import _build_in_memory_db
    from sqlglot import exp

    import sqlglot

    from quwarts.core.router.registry import get_corpus
    from quwarts.eval.router_execute_v3 import DATASET
    from quwarts.experiments.synthesize_case80 import gold_name

    spec = get_corpus(corpus)
    gold = _build_in_memory_db(load_ground_truth(gold_name(DATASET[spec.name])))
    values = column_values(corpus)
    tokens = column_tokens(values)
    context = {r["id"]: r["sql"] for r in rows}
    from quwarts.core.router.workload_features import table_attribute_names

    table_attrs = table_attribute_names(spec, context)
    used_eq: dict[str, set[str]] = {}
    used_core: dict[str, set[str]] = {}
    for r in build:
        eq, like = sites(sqlglot.parse_one(r["sql"], read="sqlite"), table_attrs)
        for lit, col, _node in eq:
            used_eq.setdefault(col, set()).add(lit.this)
        for _lit, col, core in like:
            used_core.setdefault(col, set()).add(core.casefold())
    known = {r["sql"].strip() for r in rows}
    rng = random.Random(1000 + seed)
    rounds: list[list[dict]] = [[] for _ in range(VARIANTS_PER_QUERY)]
    for r in rows:
        tree = sqlglot.parse_one(r["sql"], read="sqlite")
        eq0, like0 = sites(tree, table_attrs)
        if not eq0 and not like0:
            continue
        made = 0
        for _attempt in range(6 * VARIANTS_PER_QUERY):
            if made >= VARIANTS_PER_QUERY:
                break
            t = tree.copy()
            eq, like = sites(t, table_attrs)
            replaced, ok = 0, True
            chosen: dict[int, set[str]] = {}
            for lit, col, node in eq:
                pool = [(v, n) for v, n in values.get(col, Counter()).items()
                        if v not in used_eq.get(col, set()) and v not in chosen.setdefault(id(node), set())]
                if not pool:
                    ok = False
                    break
                v = matched(rng, pool, values.get(col, Counter()).get(lit.this, 0))
                chosen[id(node)].add(v)
                lit.replace(exp.Literal.string(v))
                replaced += 1
            if not ok:
                break
            def eligible(site) -> bool:
                """A WHERE pattern, or the only pattern of a CASE branch labelled with its own core."""

                lit_, _col, core_ = site
                branch_ = lit_.find_ancestor(exp.If)
                if branch_ is None:
                    return lit_.find_ancestor(exp.Case) is None
                label_ = branch_.args.get("true")
                n_like = len(list(branch_.this.find_all(exp.Like, exp.ILike))) if branch_.this is not None else 0
                return (n_like == 1 and isinstance(label_, exp.Literal) and label_.is_string
                        and label_.this.casefold() == core_.casefold())

            like = [x for x in like if eligible(x)]
            if like:
                lit, col, core = like[rng.randrange(len(like))]
                cores = {c.casefold() for _l, c2, c in like if c2 == col}
                pool = [(w, n) for w, n in tokens.get(col, Counter()).items()
                        if w.casefold() not in used_core.get(col, set()) and w.casefold() not in cores]
                if pool:
                    w = matched(rng, pool, tokens.get(col, Counter()).get(core, 0) or cells_with(values.get(col, Counter()), core))
                    # keep the old core's case (a lower-case pattern under LOWER(col) must stay lower case)
                    w = w.lower() if core.islower() else w.upper() if core.isupper() else w
                    branch = lit.find_ancestor(exp.If)
                    if branch is not None:
                        label = branch.args.get("true")
                        if isinstance(label, exp.Literal) and label.is_string and label.this.casefold() == core.casefold():
                            label.replace(exp.Literal.string(w))
                    lit.replace(exp.Literal.string(lit.this.replace(core, w)))
                    replaced += 1
            if not replaced:
                break
            sql = t.sql(dialect="sqlite")
            if sql.strip() in known:
                continue
            try:
                got = gold.execute(sql).fetchall()
            except sqlite3.Error:
                continue
            if any(any(v is not None and str(v).strip() != "" for v in row) for row in got):
                digest = hashlib.sha256(sql.encode()).hexdigest()[:8]
                rounds[made].append({**r, "id": f"value:{r['id']}:{digest}", "sql": sql, "sources": ["value-drift:" + r["id"]],
                                     "derived_from": r["id"], "literals": None})
                known.add(sql.strip())
                made += 1
    for batch in rounds:
        rng.shuffle(batch)
    return [v for batch in rounds for v in batch]


OPERATORS = {"Join": "join", "Group": "group", "Having": "having", "Case": "case", "In": "in", "Like": "like",
             "ILike": "like", "EQ": "eq", "NEQ": "neq", "GT": "range", "GTE": "range", "LT": "range", "LTE": "range",
             "Between": "range", "Count": "count", "Sum": "sum", "Avg": "avg", "Min": "min", "Max": "max",
             "Distinct": "distinct", "Order": "order", "Limit": "limit", "Subquery": "subquery", "Cast": "cast",
             "Div": "arith", "Mul": "arith", "Add": "arith", "Sub": "arith", "Is": "null_test", "Or": "or"}


def shape(sql: str) -> str:
    """The query's operator profile: which operators and clauses it uses (join, group, having, case, in,
    like, comparisons, aggregates, distinct, order, subquery, casts, arithmetic, OR), names and constants
    ignored. QB5000 templates keep column names and are nearly unique per query in these pools; the
    operator profile is the structural axis."""

    import sqlglot

    tree = sqlglot.parse_one(sql, read="sqlite")
    return ",".join(sorted({OPERATORS[type(n).__name__] for n in tree.walk() if type(n).__name__ in OPERATORS}))


def js(p: Counter, q: Counter) -> float:
    import math

    tp, tq = sum(p.values()) or 1, sum(q.values()) or 1
    keys = set(p) | set(q)
    m = {k: 0.5 * (p[k] / tp + q[k] / tq) for k in keys}
    kl = lambda a, t: sum((a[k] / t) * math.log2((a[k] / t) / m[k]) for k in keys if a[k])  # noqa: E731
    return 0.5 * kl(p, tp) + 0.5 * kl(q, tq)


def characterize(build: list[dict], stream: list[dict]) -> dict[str, Any]:
    from quwarts.core.adapt import drift as D

    b_attrs = set().union(*(attrs_of(r) for r in build))
    b_feats = {f for r in build for f in r["features"]}
    b_tmpl = {r["template"] for r in build}
    b_shape = {shape(r["sql"]) for r in build}
    fb = Counter(f for r in build for f in r["features"])
    fs = Counter(f for r in stream for f in r["features"])
    b_lits = {(k.lower(), v) for r in build for k, vs in (r.get("literals") or {}).items() for v in vs}
    n = len(stream) or 1
    novel_attr = [attrs_of(r) - b_attrs for r in stream]
    lit_novel = 0
    for r in stream:
        lits = {(k.lower(), v) for k, vs in (r.get("literals") or {}).items() for v in vs}
        lit_novel += bool(lits - b_lits)
    reps_b = [frozenset(r["features"]) for r in build]
    reps_s = [frozenset(r["features"]) for r in stream]
    feats = set().union(*reps_b, *reps_s) if stream else set()
    delta = D.distance(D.vector(reps_b), D.vector(reps_s), len(feats)) if stream else 0.0
    return {"queries": len(stream),
            "attribute_novel": round(sum(bool(x) for x in novel_attr) / n, 3),
            "new_attributes_per_query": round(sum(len(x) for x in novel_attr) / n, 2),
            "feature_novel": round(sum(bool(set(r["features"]) - b_feats) for r in stream) / n, 3),
            "template_novel": round(sum(r["template"] not in b_tmpl for r in stream) / n, 3),
            "shape_novel": round(sum(shape(r["sql"]) not in b_shape for r in stream) / n, 3),
            "constant_novel": round(lit_novel / n, 3),
            "unseen_feature_mass": round(sum(c for f, c in fs.items() if f not in fb) / max(1, sum(fs.values())), 3),
            "js_features": round(js(fb, fs), 3),
            "delta": round(float(delta), 4)}


def literals_of(sql: str, table_attrs: dict[str, set[str]]) -> dict[str, list[str]]:
    """Constants per column: equality values, and ``LIKE`` cores as ``~core`` (case folded)."""

    import sqlglot

    eq, like = sites(sqlglot.parse_one(sql, read="sqlite"), table_attrs)
    out: dict[str, set] = {}
    for lit, col, _node in eq:
        out.setdefault(col, set()).add(lit.this)
    for _lit, col, core in like:
        out.setdefault(col, set()).add("~" + core.casefold())
    return {k: sorted(v) for k, v in out.items()}


def design(corpus: str) -> dict[str, Any]:
    from quwarts.core.router.registry import get_corpus

    spec = get_corpus(corpus)
    rows = usable(corpus)
    context = {r["id"]: r["sql"] for r in rows}
    from quwarts.core.router.workload_features import table_attribute_names

    table_attrs = table_attribute_names(spec, context)
    for r in rows:  # constants per column (the same definition as the value variants)
        r["literals"] = literals_of(r["sql"], table_attrs)
    part = bisect([attrs_of(r) for r in rows])
    focus = set(part["focus"])
    inside = [r for r in rows if attrs_of(r) <= focus]
    outside = [r for r in rows if not attrs_of(r) <= focus]
    out: dict[str, Any] = {"corpus": corpus, "pool": len(rows), "attributes": len(part["order"]),
                           "focus": part["focus"], "focus_share": round(len(focus) / len(part["order"]), 3),
                           "cut_share": part["cut_share"], "inside": len(inside), "attribute_drift_pool": len(outside),
                           "seeds": {}}
    folder = ROOT / corpus
    # One build workload per corpus (the build's extraction is a real read informed by W0 alone; seeds
    # vary the streams, not the build).
    split_rng = random.Random(BUILD_SEED)
    ins = sorted(inside, key=lambda r: r["id"])
    split_rng.shuffle(ins)
    k = round(BUILD_SHARE * len(ins))
    build_fixed, t0_fixed = ins[:k], ins[k:]
    variants_fixed = value_variants(corpus, ins, build_fixed, BUILD_SEED)
    by_id = {r["id"]: r for r in rows}
    for v in variants_fixed:
        v["literals"] = literals_of(v["sql"], table_attrs)
        v["features"] = by_id[v["derived_from"]]["features"]
        v["template"] = by_id[v["derived_from"]]["template"]
    (folder / "build.json").write_text(json.dumps({"corpus": corpus, "focus": part["focus"],
                                                    "build": {r["id"]: r["sql"] for r in build_fixed}}, indent=1))
    for seed in SEEDS:
        rng = random.Random(seed)
        build, t0 = build_fixed, list(t0_fixed)
        variants = list(variants_fixed)
        attr_pool = sorted(outside, key=lambda r: r["id"])
        rng.shuffle(attr_pool)
        rng.shuffle(t0)
        # value variants stay round-robin over sources; the seed permutes within each round
        rounds: dict[int, list] = {}
        seen_src: Counter = Counter()
        for v in variants:
            rounds.setdefault(seen_src[v["derived_from"]], []).append(v)
            seen_src[v["derived_from"]] += 1
        variants = [v for rnd in sorted(rounds) for v in rng.sample(rounds[rnd], len(rounds[rnd]))]
        combined = [x for pair in itertools.zip_longest(attr_pool, variants) for x in pair if x is not None]
        pools = {"attribute": attr_pool, "value": variants, "combined": combined}
        streams, stats = {}, {}
        for axis in AXES:
            for p in LEVELS:
                d = round(N * p / 100)
                if d > len(pools[axis]) or N - d > len(t0):
                    stats[f"{axis}/{p}"] = {"skipped": f"drift pool {len(pools[axis])}, in-distribution {len(t0)}"}
                    continue
                stream = pools[axis][:d] + t0[:N - d]
                random.Random(seed * 100 + p).shuffle(stream)
                streams[f"{axis}/{p}"] = [r["id"] for r in stream]
                stats[f"{axis}/{p}"] = characterize(build, stream)
            # gradual: 2N queries, drift probability rising linearly
            g_rng = random.Random(seed * 7 + 3)
            drifted, stay = list(pools[axis]), list(t0)
            gradual = []
            for i in range(2 * N):
                pick_drift = g_rng.random() < i / (2 * N - 1)
                src = drifted if (pick_drift and drifted) or not stay else stay
                if not src:
                    break
                gradual.append(src.pop(0))
            streams[f"{axis}/gradual"] = [r["id"] for r in gradual]
            stats[f"{axis}/gradual"] = characterize(build, gradual)
        catalog = {r["id"]: {"sql": r["sql"], "sources": r["sources"], "attributes": r["attributes"], "features": r["features"],
                             "template": r["template"], "literals": r.get("literals"), "derived_from": r.get("derived_from")}
                   for r in rows + variants}
        payload = {"corpus": corpus, "seed": seed, "focus": part["focus"], "build": [r["id"] for r in build],
                   "in_distribution": [r["id"] for r in t0], "attribute_pool": [r["id"] for r in attr_pool],
                   "value_pool": [r["id"] for r in variants], "streams": streams, "characterization": stats,
                   "build_profile": {"queries": len(build), "attributes": len(set().union(*(attrs_of(r) for r in build))),
                                     "features": len({f for r in build for f in r["features"]}),
                                     "with_constants": sum(bool(r.get("literals")) for r in build)},
                   "queries": catalog}
        (folder / f"design_seed{seed}.json").write_text(json.dumps(payload, indent=1))
        out["seeds"][seed] = {"build": len(build), "in_distribution": len(t0), "value_pool": len(variants),
                              "characterization": stats}
    (folder / "design_summary.json").write_text(json.dumps(out, indent=1))
    return out


def report() -> str:
    lines = ["# Drift design: build workloads and streams", "",
             "| Corpus | pool | attributes | build focus (share) | cut share | inside focus | attribute-drift pool | "
             "build / in-dist / value pool (seed 0) |", "|---|---:|---:|---:|---:|---:|---:|---|"]
    summaries = {}
    for corpus in CORPORA:
        path = ROOT / corpus / "design_summary.json"
        if not path.exists():
            continue
        s = json.loads(path.read_text())
        summaries[corpus] = s
        s0 = s["seeds"]["0"]
        lines.append(f"| {corpus} | {s['pool']} | {s['attributes']} | {len(s['focus'])} ({s['focus_share']}) | {s['cut_share']} | "
                     f"{s['inside']} | {s['attribute_drift_pool']} | {s0['build']} / {s0['in_distribution']} / {s0['value_pool']} |")
    lines += ["", "Drift characterization (mean over seeds; per stream against its build workload):", "",
              "| Corpus | Axis | Level | attribute-novel | new attributes / query | feature-novel | unseen feature mass | JS (features) | shape-novel | constant-novel | CliffGuard delta |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for corpus, s in summaries.items():
        for axis in AXES:
            for p in [*LEVELS, "gradual"]:
                cells = [x["characterization"].get(f"{axis}/{p}") for x in s["seeds"].values()]
                cells = [c for c in cells if c and "skipped" not in c]
                if not cells:
                    lines.append(f"| {corpus} | {axis} | {p} | skipped | | | | | | | |")
                    continue
                m = lambda k: sum(c[k] for c in cells) / len(cells)  # noqa: E731
                lines.append(f"| {corpus} | {axis} | {p} | {m('attribute_novel'):.2f} | {m('new_attributes_per_query'):.2f} | "
                             f"{m('feature_novel'):.2f} | {m('unseen_feature_mass'):.2f} | {m('js_features'):.3f} | {m('shape_novel'):.2f} | "
                             f"{m('constant_novel'):.2f} | {m('delta'):.4f} |")
    text = "\n".join(lines)
    (ROOT / "DESIGN.md").write_text(text + "\n")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", choices=CORPORA)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    if args.corpus:
        s = design(args.corpus)
        print(json.dumps({k: v for k, v in s.items() if k != "seeds"}))
        print(json.dumps({seed: {k: v for k, v in x.items() if k != "characterization"} for seed, x in s["seeds"].items()}))
    if args.report:
        print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())

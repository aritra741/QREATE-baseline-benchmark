"""Controlled workload-drift query sets for QuWARTS (built only; nothing here calls a model).

Frozen train set. The reference workload is the 80% input split of the case80 workload (seed 42), the
split every QuWARTS build and the DocETL comparison use. It is frozen here as ids, SQL and a hash; the 0%
drift point is that set itself, whose results already exist (``score_blank.json``, ``input_split``).

What drift is. Queries are represented as in CliffGuard (Mozafari et al., SIGMOD 2015, delta_separate):
the set of (column, clause) pairs they use, with clauses select, where and group by. A query drifts from
the train set when it uses a pair no train query uses. The kinds of drift follow the workload-shift
taxonomy of Negi et al. (VLDB 2023): filters on new columns, new grouping columns, new aggregated or
projected columns.

Drifted queries. Each is a train query changed by one operator, keeping its shape (pack, CASE bucketing,
HAVING, joins): *replace* one column by another column of the same table and kind (numeric or
categorical, from the benchmark schema) that the query does not use, the neighbourhood CliffGuard
perturbs a workload in (a change of the query's column set); or *add* a filter on a column the train set
never filters on, or a grouping column it never groups by (Negi et al.'s filters on new columns).
Replacements are tried first; additions fill the pool where the train set already uses most columns. Every constant compared with the new column is
re-drawn from that column's values in the ground truth (the median, the quartiles for BETWEEN, frequent
values for = / IN, distinct frequent words for successive LIKE patterns), as the benchmark's own queries
were written against its data; the system never sees these tables. An identifier-like text column (more
than 90% distinct values: names, titles) may appear behind LIKE, but is not grouped by or compared with =
/ IN (one group or one row per entity), unless its table is a smaller dimension joined to a larger one
(team names grouped over players). A mutant is kept only if it uses at least one (column, clause) pair absent from the
train set, executes on the ground-truth tables, and returns at least one row with a non-null value.

Drift levels. The query set at level d has as many queries as the train set: a share d of drifted
queries and 1 - d of train queries, the mixture construction of gradual concept drift (Gama et al., ACM
Computing Surveys 2014). Levels are nested (the drifted queries at 25% are among those at 50%, and so on)
so the levels differ only in the amount of drift. Each set records its CliffGuard distance from the train
set and the share of its (column, clause) occurrences that the train set never uses, which grow with d.

    python -m quwarts.eval.drift_sets --corpus legal          # writes results/drift_eval/legal/
    python -m quwarts.eval.drift_sets --all                   # Med, Legal, Art, CSPaper, Player (not Finan)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
import statistics
import sys
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from quwarts.core.adapt import drift as D
from quwarts.core.router.registry import RESULTS

CORPORA = ["med", "legal", "art", "cspaper", "player"]  # every corpus but Finan (SEC filings)
LEVELS = [0.25, 0.50, 0.75, 1.00]
SEED = 20260930
PER_TRAIN_QUERY = 8  # drifted variants kept per train query (pool size)
ROOT = RESULTS / "drift_eval"
COMPARISONS = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Like, exp.In, exp.Between)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def gold_connection(corpus: str) -> sqlite3.Connection:
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.eval.router_execute_v3 import DATASET
    from quwarts.experiments.synthesize_case80 import gold_name
    from spp.config_grid import _build_in_memory_db

    return _build_in_memory_db(load_ground_truth(gold_name(DATASET[corpus])))


def schema_kinds(spec, gold: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """Per table, each benchmark attribute present in the ground truth: 'numeric' or 'categorical'."""

    from quwarts.core.router.context_probe import declared_choices

    attrs = spec.benchmark_attribute_descriptions(purpose="protocol")
    out = {}
    for t in spec.tables:
        try:
            gold_cols = {r[1].lower() for r in gold.execute(f'PRAGMA table_info("{t.sql_name}")')}
        except sqlite3.OperationalError:
            gold_cols = set()
        kinds = {}
        for name, record in attrs.get(t.attributes_key, {}).items():
            if name.lower() not in gold_cols:
                continue
            raw = str(record.get("value_type") or "str")
            choices, _multi = declared_choices(str(record.get("description") or ""))
            labels = choices and not all(c.replace(".", "", 1).lstrip("-").isdigit() for c in choices)
            # Declared numbers are numeric; so are columns typed as text whose ground-truth values are
            # numbers with at least five distinct values (years, amounts), but not 0/1 codes or labels.
            vals = [str(r[0]).strip() for r in gold.execute(
                f'SELECT "{name}" FROM "{t.sql_name}" WHERE "{name}" IS NOT NULL AND TRIM(CAST("{name}" AS TEXT)) != \'\'')]
            def num(v: str) -> bool:
                try:
                    float(v.replace(",", ""))
                    return True
                except ValueError:
                    return False
            looks = bool(vals) and sum(map(num, vals)) >= 0.95 * len(vals) and len(set(vals)) >= 5
            kinds[name] = "numeric" if not labels and (raw in ("int", "float") or looks) else "categorical"
        out[t.sql_name] = kinds
    return out


class Values:
    """Ground-truth values of a column, for re-drawing constants."""

    def __init__(self, gold: sqlite3.Connection):
        self.gold, self.cache = gold, {}

    def get(self, table: str, col: str, kind: str) -> list:
        key = (table, col)
        if key not in self.cache:
            rows = [r[0] for r in self.gold.execute(
                f'SELECT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL AND TRIM(CAST("{col}" AS TEXT)) != \'\'')]
            if kind == "numeric":
                vals = []
                for v in rows:
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        pass
                self.cache[key] = sorted(vals)
            else:
                counts: dict[str, int] = {}
                for v in rows:
                    s = str(v).strip()
                    counts[s] = counts.get(s, 0) + 1
                self.cache[key] = [v for v, _n in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
        return self.cache[key]


def _identifier_like(self, table: str, col: str, kind: str) -> bool:
    """Mostly unique text values (names, titles): not used as a new grouping or filter column."""

    if kind != "categorical":
        return False
    key = ("id", table, col)
    if key not in self.cache:
        rows = [str(r[0]).strip() for r in self.gold.execute(
            f'SELECT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL AND TRIM(CAST("{col}" AS TEXT)) != \'\'')]
        self.cache[key] = not rows or len(set(rows)) > 0.9 * len(rows)
    return self.cache[key]


Values.identifier = _identifier_like


def _number(v: float) -> exp.Literal:
    return exp.Literal.number(int(v) if float(v).is_integer() else round(v, 4))


def like_words(values: list) -> list[str]:
    """Distinct leading words of a column's frequent values, for LIKE patterns."""

    out: list[str] = []
    for v in values:
        for w in v.replace("||", " ").split():
            w = w.strip(".,;:()").lower()
            if len(w) > 3 and w not in out:
                out.append(w)
                break
    return out or [str(values[0])]


def reground(node: exp.Expression, kind: str, values: list, rng: random.Random, uses: dict | None = None) -> bool:
    """Re-draw the constants of one comparison on the new column. False if the column has no usable values."""

    lits = [lit for lit in node.find_all(exp.Literal) if not (lit.is_string and lit.this == "")]
    if not lits:
        return True
    if not values:
        return False
    if kind == "numeric":
        q = statistics.quantiles(values, n=4) if len(values) >= 4 else [values[0], values[len(values) // 2], values[-1]]
        if isinstance(node, exp.Between):
            node.set("low", _number(q[0]))
            node.set("high", _number(q[2]))
        elif isinstance(node, exp.In):
            distinct = sorted(set(values))
            node.set("expressions", [_number(v) for v in rng.sample(distinct, min(len(distinct), len(lits)))])
        else:
            for lit in lits:
                lit.replace(_number(q[1]))
        return True
    top = values[:8]
    if isinstance(node, exp.In):
        node.set("expressions", [exp.Literal.string(v) for v in top[: max(1, len(lits))]])
    elif isinstance(node, exp.Like):
        words = like_words(values[:50])
        i = uses.setdefault("like", 0) if uses is not None else 0
        if uses is not None:
            uses["like"] = i + 1  # successive LIKE branches on the column get different words
        for lit in lits:
            lit.replace(exp.Literal.string(f"%{words[i % len(words)]}%"))
    else:
        for lit in lits:
            lit.replace(exp.Literal.string(rng.choice(top[:3])))
    return True


def mutants(sql: str, kinds: dict[str, dict[str, str]], train_features: set[str], values: Values,
            gold: sqlite3.Connection, rng: random.Random, limit: int) -> list[dict[str, Any]]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    tables = set(alias.values())
    outputs = {a.alias for a in tree.find_all(exp.Alias) if a.alias}

    sizes = {t: gold.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}

    def degenerate(t: str, c2: str, kind: str) -> bool:
        """Grouping by (or equality on) an identifier-like column gives one group per entity, unless its table
        is a dimension joined to a larger one (team names grouped over players)."""

        dimension = len(tables) > 1 and sizes[t] < max(sizes.values())
        return values.identifier(t, c2, kind) and not dimension

    def owner(col: exp.Column) -> str | None:
        if col.table:
            return alias.get(col.table)
        return next(iter(tables)) if len(tables) == 1 else None

    used: dict[str, set[str]] = {}
    for col in tree.find_all(exp.Column):
        t = owner(col)
        if t and col.name in kinds.get(t, {}) and col.name not in outputs:
            used.setdefault(t, set()).add(col.name)
    options = [(t, c, c2) for t, cols in used.items() for c in sorted(cols)
               for c2 in sorted(kinds[t]) if c2 not in cols and kinds[t][c2] == kinds[t][c]]
    rng.shuffle(options)
    out, seen = [], set()
    for t, c, c2 in options:
        if len(out) >= limit:
            break
        new = tree.copy()
        for col in new.find_all(exp.Column):
            if col.name == c and owner(col) == t:
                col.set("this", exp.to_identifier(c2))
        ok, uses = True, {}
        for node in list(new.find_all(*COMPARISONS)):
            if any(col.name == c2 and owner(col) == t for col in node.find_all(exp.Column)):
                ok = ok and reground(node, kinds[t][c2], values.get(t, c2, kinds[t][c2]), rng, uses)
        if not ok:
            continue
        if degenerate(t, c2, kinds[t][c2]):
            # An identifier-like column is fine behind LIKE, but grouping by it or comparing it with = / IN
            # makes one group or one row per entity.
            grouped = new.args.get("group") and any(col.name == c2 for col in new.args["group"].find_all(exp.Column))
            exact = any(any(col.name == c2 for col in n.find_all(exp.Column)) for n in new.find_all(exp.EQ, exp.In))
            if grouped or exact:
                continue
        sql2 = new.sql(dialect="sqlite")
        if sql2 in seen:
            continue
        novel = D.representation(sql2) - train_features
        if not novel:
            continue
        try:
            rows = gold.execute(sql2).fetchall()
        except sqlite3.Error:
            continue
        if not rows or not any(v is not None for r in rows for v in r):
            continue
        seen.add(sql2)
        rep = D.representation(sql2)
        out.append({"sql": sql2, "operator": "replace", "table": t, "replaced": c, "by": c2, "kind": kinds[t][c],
                    "novel_features": sorted(novel), "novel_share": round(len(novel) / max(1, len(rep)), 3),
                    "gold_rows": len(rows)})
    # Second operator (Negi et al.'s "filters on new columns"; CliffGuard's added column): a conjunct on a
    # column the train set never filters on, or a grouping column it never groups by, added to the query.
    inv = {v: k for k, v in alias.items()}
    extra = [(op, t, c2) for t in sorted(tables) for c2 in sorted(kinds.get(t, {}))
             for op in ("filter", "group") if f"{c2}@{'where' if op == 'filter' else 'group'}" not in train_features]
    rng.shuffle(extra)
    for op, t, c2 in extra:
        if len(out) >= limit:
            break
        kind = kinds[t][c2]
        col = exp.column(c2, table=inv.get(t) if len(tables) > 1 else None)
        new = tree.copy()
        if op == "filter":
            vals = values.get(t, c2, kind)
            if not vals:
                continue
            if kind == "numeric":
                q = statistics.quantiles(vals, n=4) if len(vals) >= 4 else [vals[len(vals) // 2]] * 3
                cond = exp.GTE(this=col, expression=_number(q[1]))
            elif values.identifier(t, c2, kind):
                cond = exp.Like(this=col, expression=exp.Literal.string(f"%{like_words(vals[:50])[0]}%"))
            else:
                cond = exp.EQ(this=col, expression=exp.Literal.string(rng.choice(vals[:3])))
            where = new.args.get("where")
            new.set("where", exp.Where(this=exp.and_(where.this, cond) if where else cond))
        else:
            if kind != "categorical" or not new.args.get("group") or degenerate(t, c2, kind):
                continue
            new.args["group"].append("expressions", col.copy())
            new.append("expressions", col.copy())
        sql2 = new.sql(dialect="sqlite")
        novel = D.representation(sql2) - train_features
        if sql2 in seen or not novel:
            continue
        try:
            rows = gold.execute(sql2).fetchall()
        except sqlite3.Error:
            continue
        if not rows or not any(v is not None for r in rows for v in r):
            continue
        seen.add(sql2)
        rep = D.representation(sql2)
        out.append({"sql": sql2, "operator": f"add_{op}", "table": t, "replaced": None, "by": c2, "kind": kind,
                    "novel_features": sorted(novel), "novel_share": round(len(novel) / max(1, len(rep)), 3),
                    "gold_rows": len(rows)})
    return out


def feature_drift(train: list[str], queries: list[str]) -> float:
    feats = set().union(*(D.representation(s) for s in train))
    occ = [f for s in queries for f in D.representation(s)]
    return round(sum(f not in feats for f in occ) / max(1, len(occ)), 4)


def build(corpus: str) -> dict[str, Any]:
    from quwarts.core.router.registry import get_corpus
    from quwarts.eval import router_shared_read_run as rs

    spec = get_corpus(corpus)
    train, _test = rs.workload(corpus)
    folder = ROOT / corpus
    folder.mkdir(parents=True, exist_ok=True)

    frozen = {"corpus": corpus, "split": "case80 input split (split_80_20, seed 42)", "queries": len(train),
              "sha256": sha(json.dumps([[r["query_id"], r["sql"]] for r in train])),
              "rows": [{"query_id": r["query_id"], "sql": r["sql"]} for r in train]}
    prior = folder / "frozen_train.json"
    if prior.exists() and json.loads(prior.read_text())["sha256"] != frozen["sha256"]:
        raise SystemExit(f"{corpus}: the train split differs from the frozen one")
    prior.write_text(json.dumps(frozen, indent=1))

    gold = gold_connection(corpus)
    kinds = schema_kinds(spec, gold)
    values = Values(gold)
    train_sql = [r["sql"] for r in train]
    train_features = set().union(*(D.representation(s) for s in train_sql))
    rng = random.Random(f"{SEED}:{corpus}")
    pool = []
    for r in train:
        for i, m in enumerate(mutants(r["sql"], kinds, train_features, values, gold, rng, PER_TRAIN_QUERY)):
            pool.append({"query_id": f"{corpus}_drift:{r['query_id'].replace(':', '.')}.{i}", "source": r["query_id"], **m})
    (folder / "drift_pool.json").write_text(json.dumps(pool, indent=1))

    n = len(train)
    order = list(range(len(pool)))
    rng.shuffle(order)
    # Spread the drifted queries over source queries: round-robin over sources in shuffled order.
    by_source: dict[str, list[int]] = {}
    for i in order:
        by_source.setdefault(pool[i]["source"], []).append(i)
    spread, sources = [], list(by_source)
    rng.shuffle(sources)
    while any(by_source.values()):
        for s in sources:
            if by_source[s]:
                spread.append(by_source[s].pop(0))
    train_order = list(range(n))
    rng.shuffle(train_order)
    summary = {"corpus": corpus, "train_queries": n, "pool": len(pool), "levels": {}}
    for level in LEVELS:
        k = round(level * n)
        drifted = [pool[i] for i in spread[:k]]
        kept = [train[j] for j in train_order[: n - k]]
        rows = ([{"query_id": r["query_id"], "sql": r["sql"], "drifted": False} for r in kept] +
                [{"query_id": d["query_id"], "sql": d["sql"], "drifted": True, "source": d["source"],
                  "operator": d["operator"], "replaced": f"{d['table']}.{d['replaced']}" if d["replaced"] else None,
                  "by": f"{d['table']}.{d['by']}",
                  "novel_features": d["novel_features"]} for d in drifted])
        sqls = [r["sql"] for r in rows]
        test = D.drift_test(train_sql, sqls)
        stats = {"queries": len(rows), "drifted": len(drifted), "short_of_pool": max(0, k - len(pool)),
                 "cliffguard_delta": test["delta"], "novel_feature_share": feature_drift(train_sql, sqls),
                 "novelty_test_p": test["p"], "sha256": sha(json.dumps(sqls))}
        (folder / f"drift_{int(level * 100)}.json").write_text(json.dumps({"level": level, **stats, "rows": rows}, indent=1))
        summary["levels"][f"{int(level * 100)}%"] = stats
    summary["levels"] = {"0%": {"queries": n, "drifted": 0, "cliffguard_delta": 0.0, "novel_feature_share": 0.0,
                                "note": "the frozen train set; results exist"}, **summary["levels"]}
    summary["kinds"] = {t: dict(sorted(k.items())) for t, k in kinds.items()}
    (folder / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", choices=CORPORA)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    for corpus in (CORPORA if args.all else [args.corpus]):
        s = build(corpus)
        print(corpus, "pool", s["pool"], {k: {x: v.get(x) for x in ("drifted", "cliffguard_delta", "novel_feature_share", "short_of_pool")}
                                           for k, v in s["levels"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())

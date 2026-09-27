"""Constant sweep (AUDIT: reads gold): do answers stay right when a query's constants change?

A template's constants change with every use, so a system built from a workload must answer the
same template for constants it never saw. For every query of the workload, this makes variants that
change one comparison constant (WHERE / HAVING / CASE conditions) to another value of that column's
real domain (from the gold table, audit only): the 4 most frequent other labels for a text column,
the 4 nearest other values for a numeric one. Variants whose gold answer is empty are dropped; at
most 12 variants per query. Each variant is scored on each system's database with the benchmark
metric (raw SQL: the official rewrite is the identity on these databases, checked 80/80), and
tagged seen/unseen by whether the system's INPUT workload compared that column with that constant.
Unseen constants are rarer on average, so results are also split by the gold frequency of the
substituted value.

    python -m quwarts.eval.router_constant_sweep --corpus legal --system random=legal/shared_read_per_attribute/read_first_blank.db:random
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from quwarts.core.router.registry import RESULTS, get_corpus
from quwarts.core.router.templates import COMPARISONS, drift_split, literals
from quwarts.eval.router_execute_v3 import DATASET
from quwarts.experiments.player_case80 import score_split, split_80_20
from quwarts.experiments.single_table_case80 import load_queries

K_PER_CONSTANT = 4
MAX_VARIANTS = 12
SEED = 42


def _comparison_column(lit: exp.Literal) -> str | None:
    node = lit.parent
    while node is not None and not isinstance(node, COMPARISONS):
        node = node.parent
    if node is None:
        return None
    cols = {c.name for c in node.find_all(exp.Column)}
    return next(iter(cols)) if len(cols) == 1 else None


def _as_number(text: str) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def domains(gold_rows: list[dict[str, Any]]) -> dict[str, list[tuple[str, int]]]:
    """Per column: (value, frequency) over non-empty gold values, most frequent first."""
    out: dict[str, Counter] = defaultdict(Counter)
    for row in gold_rows:
        for col, value in row.items():
            text = "" if value is None else str(value).strip()
            if text and "||" not in text:
                out[col][text] += 1
    return {c: counter.most_common() for c, counter in out.items()}


def variants(qid: str, sql: str, domain: dict[str, list[tuple[str, int]]]) -> list[dict[str, Any]]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    lits = list(tree.find_all(exp.Literal))
    made = []
    for i, lit in enumerate(lits):
        col = _comparison_column(lit)
        if col is None or col not in domain:
            continue
        siblings = set()
        if isinstance(lit.parent, exp.In):
            siblings = {e.this for e in lit.parent.expressions if isinstance(e, exp.Literal)}
        values = [(v, f) for v, f in domain[col] if v != lit.this and v not in siblings]
        if lit.is_string:
            chosen = values[:K_PER_CONSTANT]
        else:
            base = _as_number(lit.this)
            numeric = [(v, f) for v, f in values if _as_number(v) is not None]
            if base is None or not numeric:
                continue
            chosen = sorted(numeric, key=lambda vf: (abs(_as_number(vf[0]) - base), _as_number(vf[0])))[:K_PER_CONSTANT]
        for value, freq in chosen:
            copy = tree.copy()
            target = list(copy.find_all(exp.Literal))[i]
            new = exp.Literal.string(value) if lit.is_string else exp.Literal.number(value)
            target.replace(new)
            if any(_as_number(b.args["low"].name) is not None and _as_number(b.args["high"].name) is not None
                   and _as_number(b.args["low"].name) > _as_number(b.args["high"].name)
                   for b in copy.find_all(exp.Between)):
                continue  # an empty range is not a use of the template
            made.append({"query_id": f"{qid}~{len(made)}", "base": qid, "column": col, "old": lit.this,
                         "new": value, "freq": freq, "sql": copy.sql(dialect="sqlite")})
    rng = random.Random(f"{SEED}:{qid}")
    return made if len(made) <= MAX_VARIANTS else sorted(rng.sample(made, MAX_VARIANTS), key=lambda v: v["query_id"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--system", action="append", required=True,
                        help="name=relative/db/path:split  (split: random, drift or drift_v0)")
    parser.add_argument("--out", default="constant_sweep.json")
    args = parser.parse_args(argv)
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.synthesize_case80 import gold_name
    from spp.config_grid import _build_in_memory_db

    spec = get_corpus(args.corpus)
    table = spec.tables[0].sql_name
    dataset = DATASET[spec.name]
    rows = load_queries(dataset)
    gold_tables = load_ground_truth(gold_name(dataset))
    domain = domains(gold_tables[table])
    gold_conn = _build_in_memory_db(gold_tables)
    all_variants = []
    for r in rows:
        for v in variants(r["query_id"], r["sql"], domain):
            try:
                if gold_conn.execute(v["sql"]).fetchone() is None:
                    continue
            except Exception:  # noqa: BLE001
                continue
            all_variants.append(v)
    gold_conn.close()
    freq_cut = statistics.median(v["freq"] for v in all_variants)
    report: dict[str, Any] = {"audit_only": True, "n_variants": len(all_variants),
                              "n_base_queries": len({v["base"] for v in all_variants}),
                              "freq_median": freq_cut, "systems": {}}
    for item in args.system:
        name, rest = item.split("=", 1)
        db_rel, split = rest.rsplit(":", 1)
        db = RESULTS / "quwarts_router_v3" / db_rel
        train = (split_80_20(rows, SEED)[0] if split == "random"
                 else drift_split(rows, SEED, include_constants=split == "drift_v0")[0])
        train_ids = {r["query_id"] for r in train}
        seen = set().union(*(literals(r["sql"]) for r in train))
        test_rows = [{"query_id": v["query_id"], "sql": v["sql"], "pack": v["base"].split(":")[0],
                      "pred_sql": v["sql"], "pred_db": str(db)} for v in all_variants]
        base_rows = [{"query_id": r["query_id"], "sql": r["sql"], "pack": r["query_id"].split(":")[0],
                      "pred_sql": r["sql"], "pred_db": str(db)} for r in rows]
        product = lambda rep: {p["query_id"]: float(p.get("structure_f2") or 0) * float(p.get("cell_f1_20") or 0)  # noqa: E731
                               for p in rep["per_query"]}
        var_score = product(score_split(test_rows, db, gold_tables, dataset=gold_name(dataset)))
        base_score = product(score_split(base_rows, db, gold_tables, dataset=gold_name(dataset)))
        cells: dict[tuple, list[float]] = defaultdict(list)
        per_column: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for v in all_variants:
            s = var_score[v["query_id"]]
            tag = "seen" if (v["column"], v["new"]) in seen else "unseen"
            role = "input" if v["base"] in train_ids else "held_out"
            band = "frequent" if v["freq"] >= freq_cut else "rare"
            cells[(tag,)].append(s)
            cells[(tag, band)].append(s)
            cells[(tag, role)].append(s)
            per_column[v["column"]][tag].append(s)
        mean = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
        report["systems"][name] = {
            "db": db_rel, "split": split,
            "original_queries": {"input": mean([base_score[q] for q in train_ids]),
                                 "held_out": mean([base_score[r["query_id"]] for r in rows if r["query_id"] not in train_ids]),
                                 "all": mean(list(base_score.values()))},
            "variants": {"/".join(k): {"n": len(xs), "mean": mean(xs)} for k, xs in sorted(cells.items())},
            "per_column": {c: {t: {"n": len(xs), "mean": mean(xs)} for t, xs in d.items()} for c, d in sorted(per_column.items())},
            "per_variant": {v["query_id"]: round(var_score[v["query_id"]], 4) for v in all_variants},
        }
    report["variants"] = all_variants
    out = RESULTS / "quwarts_router_v3" / spec.name / args.out
    out.write_text(json.dumps(report, indent=2))
    for name, s in report["systems"].items():
        print(f"\n== {name}: original {s['original_queries']}")
        for k, v in s["variants"].items():
            print(f"   {k:22s} n={v['n']:4d} mean={v['mean']:.3f}" if v["mean"] is not None else f"   {k} n=0")
        for c, d in s["per_column"].items():
            print(f"   col {c:28s} " + "  ".join(f"{t}: n={x['n']} {x['mean']:.3f}" for t, x in d.items()))
    print(json.dumps({k: report[k] for k in ("n_variants", "n_base_queries", "freq_median")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

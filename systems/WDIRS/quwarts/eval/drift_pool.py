"""Query pools for the drift experiments: every query we have for a corpus (AUDIT: executes on gold).

Sources, per corpus:
* the benchmark's own query files (``Query/<Dataset>/**/*.sql``: Select, Filter, Agg, Mixed, Join,
  Expanded, Variations, Subsample, Splits and the rest), parsed statement by statement
* the analytical workloads the protocol runs use (the case80 packs: agg20, filter20, groupby20,
  multiagg20)

Each statement is normalized (sqlglot, sqlite dialect) and de-duplicated. A query is *scorable* if the
benchmark metric covers it (an aggregation query; the product of structure F2 and cell F1 is defined
only for those) and *valid* if it executes on the gold tables with at least one row that is not all
NULL. Recorded per query: its source, QB5000 template (constants removed), CliffGuard (column, clause)
features, the attributes of each table it reads, and its string literals per column.

    python -m quwarts.eval.drift_pool --corpus art
    python -m quwarts.eval.drift_pool --report
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from quwarts.core.router.registry import PROJECT, RESULTS

CORPORA = ["med", "finan", "legal", "art", "cspaper", "player"]
FOLDER = {"med": "Med", "finan": "Finan", "legal": "Legal", "art": "Art", "cspaper": "CSPaper", "player": "Player"}
ROOT = RESULTS / "drift_design"


def statements(path: Path) -> list[str]:
    import sqlglot

    text = path.read_text(errors="ignore")
    try:
        trees = sqlglot.parse(text, read="sqlite")
    except sqlglot.errors.ParseError:
        trees = []
        for chunk in text.split(";\n"):
            try:
                trees += sqlglot.parse(chunk, read="sqlite")
            except sqlglot.errors.ParseError:
                continue
    return [t.sql(dialect="sqlite") for t in trees if t is not None and t.find(sqlglot.exp.Select) is not None]


def sources(corpus: str) -> list[tuple[str, str, str]]:
    """(source, id, sql) for every statement we have."""

    from quwarts.eval import router_shared_read_run as rs

    out = []
    for path in sorted((PROJECT / "Query" / FOLDER[corpus]).rglob("*.sql")):
        rel = str(path.relative_to(PROJECT / "Query" / FOLDER[corpus]))
        for i, sql in enumerate(statements(path)):
            out.append((f"benchmark:{rel}", f"{rel}#{i + 1}", sql))
    train, test = rs.workload(corpus)
    for r in list(train) + list(test):
        out.append((f"case80:{r['pack']}", r["query_id"], r["sql"]))
    return out


def normalize(sql: str) -> str:
    import sqlglot

    return sqlglot.parse_one(sql, read="sqlite").sql(dialect="sqlite", normalize=True)


def pool(corpus: str) -> dict[str, Any]:
    import sqlite3

    from diagnostics.run_config_grid import load_ground_truth
    from spp.aggregation_metrics import schema_from_sql
    from spp.config_grid import _build_in_memory_db
    from quwarts.core.adapt import controller as C
    from quwarts.core.adapt import drift as D
    from quwarts.core.router.registry import get_corpus
    from quwarts.core.router.workload_features import comparison_literals, table_attribute_names
    from quwarts.eval.router_execute_v3 import DATASET
    from quwarts.experiments.synthesize_case80 import gold_name

    spec = get_corpus(corpus)
    gold = _build_in_memory_db(load_ground_truth(gold_name(DATASET[spec.name])))
    schema = {t: {r[1] for r in gold.execute(f'PRAGMA table_info("{t}")')} for (t,) in
              gold.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    seen: dict[str, dict] = {}
    for source, qid, sql in sources(corpus):
        try:
            key = normalize(sql)
        except Exception:  # noqa: BLE001
            continue
        if key in seen:
            seen[key]["sources"].append(source)
            continue
        seen[key] = {"id": qid, "sql": sql, "sources": [source]}
    rows = list(seen.values())
    context = {r["id"]: r["sql"] for r in rows}
    table_attrs = table_attribute_names(spec, context)
    out = []
    for r in rows:
        sql = r["sql"]
        rec = {**r, "template": None, "features": [], "attributes": {}, "literals": {}, "scorable": False,
               "valid": False, "gold_rows": 0, "reason": ""}
        try:
            rec["scorable"] = bool(schema_from_sql(sql).get("is_aggregation"))
            rec["template"] = D.template(sql)
            rec["features"] = sorted(D.representation(sql))
            rec["attributes"] = {t: sorted(a) for t, a in C.query_attributes(spec, r["id"], sql, context).items()}
            rec["literals"] = {k: sorted(v) for k, v in comparison_literals(sql, table_attrs).items()}
        except Exception as exc:  # noqa: BLE001
            rec["reason"] = f"parse: {exc}"[:200]
            out.append(rec)
            continue
        unknown = [f"{t}.{a}" for t, attrs in rec["attributes"].items() for a in attrs if a.lower() not in {c.lower() for c in schema.get(t, set())}]
        if unknown:
            rec["reason"] = "unknown attributes " + ", ".join(unknown[:4])
            out.append(rec)
            continue
        try:
            got = gold.execute(sql).fetchall()
        except sqlite3.Error as exc:
            rec["reason"] = f"gold: {exc}"[:200]
            out.append(rec)
            continue
        rec["gold_rows"] = len(got)
        rec["valid"] = any(any(v is not None and str(v).strip() != "" for v in row) for row in got)
        if not rec["valid"]:
            rec["reason"] = "empty on gold"
        out.append(rec)
    (ROOT / corpus).mkdir(parents=True, exist_ok=True)
    (ROOT / corpus / "pool.json").write_text(json.dumps(out, indent=1))
    usable = [x for x in out if x["valid"] and x["scorable"]]
    return {"corpus": corpus, "statements": len(sources(corpus)), "distinct": len(out), "valid": sum(x["valid"] for x in out),
            "scorable_valid": len(usable), "templates": len({x["template"] for x in usable}),
            "attributes": len({(t, a) for x in usable for t, attrs in x["attributes"].items() for a in attrs}),
            "by_source": dict(Counter(x["sources"][0].split(":", 1)[1].split("/")[0] for x in usable)),
            "reasons": dict(Counter(x["reason"].split(":")[0].split(" ")[0] for x in out if x["reason"]))}


def report() -> str:
    lines = ["| Corpus | statements | distinct | valid on gold | scorable and valid | templates | attributes | scorable, valid by source |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for corpus in CORPORA:
        path = ROOT / corpus / "pool.json"
        if not path.exists():
            continue
        rows = json.loads(path.read_text())
        usable = [x for x in rows if x["valid"] and x["scorable"]]
        src = Counter(x["sources"][0].split(":", 1)[1].split("/")[0] for x in usable)
        lines.append(f"| {corpus} | {sum(len(x['sources']) for x in rows)} | {len(rows)} | {sum(x['valid'] for x in rows)} | {len(usable)} | "
                     f"{len({x['template'] for x in usable})} | {len({(t, a) for x in usable for t, attrs in x['attributes'].items() for a in attrs})} | "
                     + ", ".join(f"{k} {v}" for k, v in src.most_common()) + " |")
    text = "\n".join(lines)
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "POOL.md").write_text(text + "\n")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", choices=CORPORA)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    if args.corpus:
        print(json.dumps(pool(args.corpus)))
    if args.report:
        print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())

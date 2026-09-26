"""One shared, workload-informed read per document, executed over a whole corpus and scored.

The reference workload given to the system is the 80% input split of the case80 workload
(``split_80_20`` with the case80 seed). The system extracts every attribute that workload
needs with one read per document: all fields, the declared schema contract (allowed values,
nullability), each field described by how the input workload uses it, and the declared
absence values applied at commit. Every query of the full workload (input + held-out
split) is then scored on the resulting database.

Primary database (pre-declared): shared-read values replace the incumbent where the read
gives a value; the incumbent is kept where it does not (``read_first``). Secondary:
additive fill of incumbent NULLs only (``fill``).

    python -m quwarts.eval.router_shared_read_run --corpus legal --reads --workers 32
    python -m quwarts.eval.router_shared_read_run --corpus legal --score
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from quwarts.core.ledger import TokenLedger
from quwarts.core.router.context_probe import field_specs
from quwarts.core.router.executor import Read, commit_value, load_values, run_reads
from quwarts.core.router.needs import query_needs
from quwarts.core.router.registry import PROJECT, RESULTS, get_corpus
from quwarts.core.router.workload_features import table_attribute_names, usage_phrase, workload_features
from quwarts.eval.router_execute_v3 import DATASET, score

SHARED = "__workload__"
SEED = 42  # the case80 split seed: its held-out 20% are exactly the 16 DocETL evaluation queries


def workload(corpus: str) -> tuple[list[dict], list[dict]]:
    from quwarts.experiments.player_case80 import split_80_20
    from quwarts.experiments.single_table_case80 import load_queries

    return split_80_20(load_queries(DATASET[corpus]), SEED)


def setup(corpus: str):
    spec = get_corpus(corpus)
    train, test = workload(corpus)
    train_q = {r["query_id"]: r["sql"] for r in train}
    table_attrs = table_attribute_names(spec)
    needs = [n for r in train for n in query_needs(r["query_id"], r["sql"], table_attrs)]
    wf = workload_features(spec, train_q)
    numeric = {q for q, u in wf["attributes"].items() if u.numeric}
    fields = field_specs(spec, needs, numeric)
    fields = {q: replace(f, usage=usage_phrase(wf["attributes"][q])) if q in wf["attributes"] else f
              for q, f in fields.items()}
    reads = []
    for table in sorted({n.table for n in needs}):
        attrs = tuple(sorted({n.attribute for n in needs if n.table == table}))
        reads.append(Read(table, SHARED, attrs))
    return spec, train, test, fields, reads


def build_db(spec, reads, values, fields, queries: dict[str, str], dest: Path, policy: str) -> dict[str, Any]:
    from quwarts.core.pipeline import official_sql
    from quwarts.core.schema_columns import complete_physical_schema
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(spec.incumbent_db, dest)
    conn = sqlite3.connect(dest)
    audit = audit_workload([{"query_id": q, "sql": s} for q, s in queries.items()])
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    complete_physical_schema(conn, queries, predicates)
    stats = {"written": 0, "kept_incumbent": 0, "no_value": 0}
    for read in reads:
        rows = {Path(str(d)).name if str(d).endswith(".txt") else f"{Path(str(d)).name}.txt": d
                for (d,) in conn.execute(f'SELECT doc_id FROM "{read.table}"')}
        for doc, got in values.get((read.table, read.context), {}).items():
            if doc not in rows:
                continue
            for attr in read.attributes:
                value = commit_value(got.get(attr), fields[f"{read.table}.{attr}"])
                if value is None:
                    stats["no_value"] += 1
                    continue
                if policy == "fill":
                    (cur,) = conn.execute(f'SELECT "{attr}" FROM "{read.table}" WHERE doc_id = ?', (rows[doc],)).fetchone()
                    if cur is not None:
                        stats["kept_incumbent"] += 1
                        continue
                conn.execute(f'UPDATE "{read.table}" SET "{attr}" = ? WHERE doc_id = ?', (value, rows[doc]))
                stats["written"] += 1
    conn.commit()
    for q, s in queries.items():  # every rewritten query must execute: errors are raised, not scored empty
        conn.execute(official_sql(s, dest, predicates, query_id=q)).fetchall()
    conn.close()
    return stats


def subset(per_query: list[dict], ids: set[str]) -> dict[str, float]:
    rows = [r for r in per_query if r["query_id"] in ids]
    mean = lambda k: sum(float(r.get(k) or 0.0) for r in rows) / len(rows) if rows else 0.0  # noqa: E731
    return {"n": len(rows), "structure_f2": mean("structure_f2"), "cell_f1_20": mean("cell_f1_20"), "product": mean("product")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--reads", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args(argv)
    spec, train, test, fields, reads = setup(args.corpus)
    out = RESULTS / "quwarts_router_v3" / spec.name / "shared_read"
    out.mkdir(parents=True, exist_ok=True)
    journal = out / "reads.jsonl"
    print(json.dumps({"input_queries": len(train), "held_out_queries": len(test),
                      "reads": [{"table": r.table, "attributes": list(r.attributes)} for r in reads]}))
    if args.reads:
        from quwarts.core.llm.openrouter import load_env_file, make_caller

        load_env_file(PROJECT / ".env")
        ledger = TokenLedger(theta=10**12)
        caller = make_caller(ledger, max_tokens=400)
        stats = run_reads(spec, reads, {r["query_id"]: r["sql"] for r in train}, fields, caller, journal, args.workers)
        stats["spent_this_run"] = ledger.spent
        print(json.dumps(stats))
    if args.score:
        values = load_values(journal)
        all_q = {r["query_id"]: r["sql"] for r in train + test}
        tokens = sum(json.loads(l)["tokens"] for l in journal.read_text().splitlines())
        report: dict[str, Any] = {"read_tokens": tokens, "calls": len(journal.read_text().splitlines())}
        dbs = {}
        for policy in ("read_first", "fill"):
            db = out / f"{policy}.db"
            report[f"{policy}_db"] = build_db(spec, reads, values, fields, all_q, db, "replace" if policy == "read_first" else "fill")
            report[f"{policy}_sha256"] = hashlib.sha256(db.read_bytes()).hexdigest()
            dbs[policy] = db
        (out / "frozen.json").write_text(json.dumps(report, indent=2))
        # Gold is read only below, after both databases are written and hashed.
        for policy, db in dbs.items():
            result = score(DATASET[spec.name], all_q, {q: str(db) for q in all_q}, db)
            report[policy] = {
                "all": subset(result["per_query"], set(all_q)),
                "input_split": subset(result["per_query"], {r["query_id"] for r in train}),
                "held_out_split": subset(result["per_query"], {r["query_id"] for r in test}),
                "per_query": result["per_query"],
            }
        (out / "score.json").write_text(json.dumps(report, indent=2))
        print(json.dumps({p: {k: v for k, v in report[p].items() if k != "per_query"} for p in dbs}, indent=2))
        print(json.dumps({"read_tokens": tokens}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

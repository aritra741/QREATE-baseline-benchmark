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


def out_dir(spec, variant: str) -> Path:
    if variant in ("described_v1", "described_v3"):
        variant = "described"  # description versions share one folder
    return RESULTS / "quwarts_router_v3" / spec.name / ("shared_read" if variant == "plain" else f"shared_read_{variant}")


def setup(corpus: str, variant: str = "plain"):
    spec = get_corpus(corpus)
    train, test = workload(corpus)
    train_q = {r["query_id"]: r["sql"] for r in train}
    table_attrs = table_attribute_names(spec, train_q)
    needs = [n for r in train for n in query_needs(r["query_id"], r["sql"], table_attrs)]
    wf = workload_features(spec, train_q)
    numeric = {q for q, u in wf["attributes"].items() if u.numeric}
    fields = field_specs(spec, needs, numeric)
    fields = {q: replace(f, usage=usage_phrase(wf["attributes"][q])) if q in wf["attributes"] else f
              for q, f in fields.items()}
    if variant in ("described", "described_v1", "described_v3", "per_attribute"):
        base = out_dir(spec, "described")
        name = {"described": "descriptions.json", "described_v1": "v1/descriptions.json",
                "described_v3": "descriptions_v3.json", "per_attribute": "descriptions_per_attribute.json"}[variant]
        frozen = json.loads((base / name).read_text())
        fields = {q: replace(f, description=frozen[q]["description"]) if q in frozen else f for q, f in fields.items()}
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


def describe(corpus: str) -> int:
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.router.describe import generate_descriptions

    spec = get_corpus(corpus)
    train, _test = workload(corpus)
    train_q = {r["query_id"]: r["sql"] for r in train}
    uses = list(workload_features(spec, train_q)["attributes"].values())
    out = out_dir(spec, "described")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "descriptions.json").exists():
        raise SystemExit("descriptions are frozen; remove descriptions.json to regenerate")
    load_env_file(PROJECT / ".env")
    ledger = TokenLedger(theta=10**12)
    caller = make_caller(ledger, max_tokens=300)
    records = generate_descriptions(spec, uses, train_q, caller, out / "describe_journal.jsonl")
    (out / "descriptions.json").write_text(json.dumps(records, indent=2, sort_keys=True))
    (out / "descriptions.sha256").write_text(hashlib.sha256((out / "descriptions.json").read_bytes()).hexdigest() + "\n")
    for q, r in records.items():
        print(f"{q}: {r['description']}")
    print(json.dumps({"describe_tokens": ledger.spent}))
    return 0


def derive_v3(corpus: str) -> int:
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.router.describe import generate_v3

    spec = get_corpus(corpus)
    train, _ = workload(corpus)
    train_q = {r["query_id"]: r["sql"] for r in train}
    uses = list(workload_features(spec, train_q)["attributes"].values())
    base = out_dir(spec, "described")
    if (base / "descriptions_v3.json").exists():
        raise SystemExit("v3 descriptions are frozen")
    load_env_file(PROJECT / ".env")
    ledger = TokenLedger(theta=10**12)
    caller = make_caller(ledger, max_tokens=300)
    v3 = generate_v3(spec, uses, train_q, caller, base / "describe_v3_journal.jsonl")
    (base / "descriptions_v3.json").write_text(json.dumps(v3, indent=2, sort_keys=True))
    for q in sorted(u.qualified for u in uses):
        print(f"{q}: {v3[q]['description'] if q in v3 else '(no description: name only)'}")
    print(json.dumps({"describe_v3_tokens": ledger.spent}))
    return 0


def choose_per_attribute(corpus: str, workers: int) -> int:
    """Pre-declared (2026-09-26, before any v3 read): per attribute, use the variant among
    plain / v2 / v3 with the highest SQL consistency on the 20-case check sample; ties go to
    the simpler variant (plain, then v3, then v2). Plain means the name alone (no description)."""

    spec = get_corpus(corpus)
    base = out_dir(spec, "described")
    report = json.loads((base / "check.json").read_text())
    if "described_v3" not in report:
        extra = _check_variants(corpus, workers, ("described_v3",))
        report.update(extra)
        (base / "check.json").write_text(json.dumps(report, indent=2))
    order = ["plain", "described_v3", "described"]
    v2 = json.loads((base / "descriptions.json").read_text())
    v3 = json.loads((base / "descriptions_v3.json").read_text())
    chosen, per = {}, {}
    for q in report["plain"]["per_attribute"]:
        best = max(order, key=lambda v: (report[v]["per_attribute"][q], -order.index(v)))
        per[q] = best
        if best == "described":
            chosen[q] = v2[q]
        elif best == "described_v3":
            chosen[q] = v3[q]
    out = out_dir(spec, "per_attribute")
    out.mkdir(parents=True, exist_ok=True)
    (out / "descriptions_per_attribute.json").write_text(json.dumps(chosen, indent=2, sort_keys=True))
    (base / "descriptions_per_attribute.json").write_text(json.dumps(chosen, indent=2, sort_keys=True))
    (out / "choice.json").write_text(json.dumps(per, indent=2, sort_keys=True))
    for q, v in per.items():
        print(f"  {q:34} -> {v}  " + " ".join(f"{k}={report[k]['per_attribute'][q]:.2f}" for k in order))
    return 0


def _numeric_literals(queries: dict[str, str], table: str, attr: str) -> set[float]:
    import sqlglot
    from sqlglot import exp

    out: set[float] = set()
    for sql in queries.values():
        for node in sqlglot.parse_one(sql, read="sqlite").find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In):
            cols = [c for c in node.find_all(exp.Column) if c.name == attr]
            if len(cols) != 1:
                continue
            for lit in node.find_all(exp.Literal):
                if not lit.is_string:
                    try:
                        out.add(float(lit.this))
                    except ValueError:
                        pass
    return out


def check(corpus: str, workers: int) -> int:
    """Pre-declared rule: use the generated descriptions iff they raise mean SQL consistency.

    Per attribute, consistency = share of sampled documents whose value has the form the SQL
    workload uses: a number where the SQL compares or aggregates numerically, 0/1 where it is
    only compared with 0 and 1, one of the compared labels where it is compared with labels,
    and any value otherwise. No gold is read.
    """

    variants = ("plain", "described_v1", "described")
    report = _check_variants(corpus, workers, variants)
    spec = get_corpus(corpus)
    report["decision"] = max(variants, key=lambda v: (report[v]["mean_consistency"], v == "plain"))
    (out_dir(spec, "described") / "check.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({v: round(report[v]["mean_consistency"], 3) for v in variants}), "decision:", report["decision"])
    for q in report["plain"]["per_attribute"]:
        print(f"  {q:34} " + " ".join(f"{v}={report[v]['per_attribute'][q]:.2f}" for v in variants))
    return 0


def _check_variants(corpus: str, workers: int, variants) -> dict[str, Any]:
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.router.comparator import as_number, as_text, is_null
    from quwarts.core.router.corpus_features import deterministic_sample, list_documents

    load_env_file(PROJECT / ".env")
    ledger = TokenLedger(theta=10**12)
    caller = make_caller(ledger, max_tokens=400)
    spec = get_corpus(corpus)
    train, _ = workload(corpus)
    train_q = {r["query_id"]: r["sql"] for r in train}
    wf = workload_features(spec, train_q)
    report: dict[str, Any] = {}
    for variant in variants:
        _s, _tr, _te, fields, reads = setup(corpus, variant)
        base = out_dir(spec, "described") / f"check_{variant}.jsonl"
        sample_spec = spec
        # Same 20 documents for both variants.
        import quwarts.core.router.executor as ex

        original = ex.list_documents
        paths = deterministic_sample(list_documents(spec.table(reads[0].table)), 20, "describe-check")
        ex.list_documents = lambda table, p=paths: p
        try:
            run_reads(sample_spec, reads, train_q, fields, caller, base, workers)
        finally:
            ex.list_documents = original
        values = load_values(base)
        per_attr = {}
        for read in reads:
            got = values.get((read.table, read.context), {})
            for attr in read.attributes:
                q = f"{read.table}.{attr}"
                use = wf["attributes"][q]
                nums = _numeric_literals(train_q, read.table, attr)
                labels = {l.lower() for l in use.literals}
                ok = 0
                for doc_vals in got.values():
                    v = doc_vals.get(attr)
                    if is_null(v):
                        continue
                    n = as_number(v)
                    if nums and nums <= {0.0, 1.0}:
                        ok += n in (0.0, 1.0)
                    elif use.numeric:
                        ok += n is not None
                    elif labels:
                        ok += any(l == as_text(part).strip().lower() for part in as_text(v).split("||") for l in labels)
                    else:
                        ok += 1
                per_attr[q] = ok / max(1, len(got))
        report[variant] = {"mean_consistency": sum(per_attr.values()) / len(per_attr), "per_attribute": per_attr,
                           "check_tokens": ledger.spent}
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--reads", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--variant", choices=["plain", "described"], default="plain")
    parser.add_argument("--describe", action="store_true", help="generate and freeze workload descriptions")
    parser.add_argument("--check", action="store_true", help="gold-free consistency check on a document sample")
    parser.add_argument("--v3", action="store_true", help="derive v3 descriptions (SQL-constrained v2)")
    parser.add_argument("--choose", action="store_true", help="pre-declared per-attribute choice of description")
    args = parser.parse_args(argv)
    if args.describe:
        return describe(args.corpus)
    if args.check:
        return check(args.corpus, args.workers)
    if args.v3:
        return derive_v3(args.corpus)
    if args.choose:
        return choose_per_attribute(args.corpus, args.workers)
    spec, train, test, fields, reads = setup(args.corpus, args.variant)
    out = out_dir(spec, args.variant)
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

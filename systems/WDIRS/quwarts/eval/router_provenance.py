"""Provenance and incremental maintenance of a shared-read QuWARTS database (``core.lineage``).

    # record where every cell comes from (no model calls)
    python -m quwarts.eval.router_provenance capture --corpus finan
    # what a new corpus version would need: per document, reads certain and conditional (no calls)
    python -m quwarts.eval.router_provenance plan --corpus finan --overlay DIR --policy facts
    # bring the database to that version (resumable; --deadline stops starting new reads)
    python -m quwarts.eval.router_provenance apply --corpus finan --overlay DIR --policy facts [--budget N]
    python -m quwarts.eval.router_provenance history --corpus finan

The run is the benchmark-protocol shared read with chained long documents on a blank base
(``router_shared_read_run --variant protocol --blank-base --long chain``). The overlay holds
``<table>/<name>.txt`` files that replace or add documents and an optional ``<table>/DELETED`` list.
``--store DIR`` points at another copy of the store (the evaluation works on copies).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def context(corpus: str):
    from quwarts.eval import router_shared_read_run as rs

    rs.BLANK_BASE, rs.TAG, rs.LONG, rs.CANONICALIZE = True, "chain", "chain", False
    spec, train, test, fields, reads = rs.setup(corpus, "protocol")
    out = rs.out_dir(spec, "protocol")
    queries = {r["query_id"]: r["sql"] for r in train + test}
    workload = {r["query_id"]: r["sql"] for r in train}
    return spec, fields, reads, queries, workload, out


def build(spec, reads, values, fields, queries, dest):
    """The builder of the shared-read run: blank base, read values first, no canonicalization."""

    from quwarts.eval import router_shared_read_run as rs

    saved = rs.BLANK_BASE, rs.CANONICALIZE
    rs.BLANK_BASE, rs.CANONICALIZE = True, False
    try:
        return rs.build_db(spec, reads, values, fields, queries, dest, "replace")
    finally:
        rs.BLANK_BASE, rs.CANONICALIZE = saved


def main(argv: list[str] | None = None) -> int:
    from quwarts.core.lineage import maintain as M
    from quwarts.core.lineage import store as S

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["capture", "plan", "apply", "history"])
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--store", type=Path, default=None, help="store folder (default: <run>/provenance)")
    parser.add_argument("--overlay", type=Path, default=None)
    parser.add_argument("--policy", choices=["exact", "facts", "answers"], default="answers")
    parser.add_argument("--attribute", action="store_true", help="commit a re-read change only if the edit explains it")
    parser.add_argument("--budget", type=int, default=None, help="token budget for new reads")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--deadline", type=float, default=None, help="seconds after which no new read starts")
    args = parser.parse_args(argv)
    spec, fields, reads, queries, workload, out = context(args.corpus)
    folder = args.store or out / "provenance"
    store = folder / "provenance.db"
    if args.action == "capture":
        report = M.capture(store, spec, reads, fields, out / "reads.jsonl", out / "read_first_blank.db", queries)
    elif args.action == "plan":
        conn = S.open_store(store)
        plans = [p for p in M.plan(conn, spec, reads, fields, args.overlay, args.policy) if p.status != "unchanged"]
        report = {"documents": [p.summary() for p in plans],
                  "certain_reads": sum(p.certain for p in plans), "conditional_reads": sum(p.conditional for p in plans),
                  "tokens_estimate": sum(p.tokens_estimate for p in plans)}
    elif args.action == "apply":
        from quwarts.core.ledger import TokenLedger
        from quwarts.core.llm.openrouter import load_env_file, make_caller
        from quwarts.core.router.registry import PROJECT

        load_env_file(PROJECT / ".env")
        caller = make_caller(TokenLedger(theta=10**12), max_tokens=600)
        report = M.apply(store, spec, reads, fields, queries, args.overlay, args.policy, caller, args.budget,
                         args.workers, args.deadline, workload, build=build, attribute=args.attribute)
    else:
        conn = S.open_store(store)
        report = {"versions": [{"version": v, "note": n, **{k: x for k, x in json.loads(s).items() if k != "plan"}}
                               for v, n, s in conn.execute("SELECT * FROM versions ORDER BY version")],
                  "last_changes": [dict(zip(("version", "table", "doc", "attr", "old", "new", "reason"), r))
                                   for r in conn.execute("SELECT * FROM history ORDER BY rowid DESC LIMIT 20")]}
    print(json.dumps(report, indent=1, default=str)[:20000])
    return 0


if __name__ == "__main__":
    sys.exit(main())

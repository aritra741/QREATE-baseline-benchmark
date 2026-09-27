"""Triggered materialization on query streams with column drift (``core.adapt``).

Stream (seeded, per corpus, from the 80% input split of the case80 workload):

* hidden columns: columns are taken in seeded random order and hidden while the input queries that use
  a hidden column stay within 30% of the split; the build workload is the input queries that use no
  hidden column;
* phase ``stable``: 30 queries drawn from the build workload, with one in eight of the hidden-column
  queries inserted at random positions (sporadic drift);
* phase ``trend``: the other hidden-column queries, alternating with build-workload queries;
* phase ``recur``: 20 queries, each a hidden-column query (drawn again) or a build query with equal chance.

The master database at the start is the benchmark-protocol run's database (chained long documents) with
the hidden columns removed: its other columns were read with the hidden fields in the prompt, the one
approximation of the setup. Costs are the controller's token estimates for every read a policy decides
on, whether or not the read journal already holds it (what a system without this experiment's shared
memo would pay); ``spent`` is what the run actually paid.

    python -m quwarts.eval.materialize_stream --corpus cspaper --dry              # all policies, no calls
    python -m quwarts.eval.materialize_stream --corpus cspaper --real --policy drift --deadline 110
    python -m quwarts.eval.materialize_stream --corpus cspaper --score            # AUDIT: reads gold
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from quwarts.core.adapt import controller as C
from quwarts.core.router.registry import RESULTS

ROOT = RESULTS / "materialize"
SEED = 20260929
HIDDEN_SHARE = 0.30


class Incomplete(Exception):
    pass


def context(corpus: str):
    from quwarts.eval import router_shared_read_run as rs
    from quwarts.core.router.corpus_features import list_documents

    rs.BLANK_BASE, rs.CANONICALIZE = True, False
    spec = rs.get_corpus(corpus)
    train, test = rs.workload(corpus)
    run = RESULTS / "quwarts_router_v3" / f"{spec.name}_chain" / "shared_read_protocol"
    if not (run / "read_first_blank.db").exists():
        run = RESULTS / "quwarts_router_v3" / spec.name / "shared_read_protocol"
    docs = {t.sql_name: {p.name: p for p in list_documents(t)} for t in spec.tables}
    return spec, train, test, run, docs


def doc_tokens(corpus: str, docs) -> dict[tuple[str, str], int]:
    from quwarts.core.retrieve_extract.tokens import count_tokens
    from quwarts.core.router.corpus_features import read_document

    cache = ROOT / corpus / "doc_tokens.json"
    if cache.exists():
        return {tuple(k.split("|", 1)): v for k, v in json.loads(cache.read_text()).items()}
    out = {(t, d): count_tokens(read_document(p)) for t, ds in docs.items() for d, p in ds.items()}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({f"{t}|{d}": v for (t, d), v in out.items()}))
    return out


def make_stream(spec, train: list[dict]) -> dict[str, Any]:
    rng = random.Random(f"{SEED}:{spec.name}")
    rows = {r["query_id"]: r["sql"] for r in train}
    attrs = {q: {f"{t}.{a}" for t, xs in C.query_attributes(spec, q, s, rows).items() for a in xs} for q, s in rows.items()}
    cols = sorted(set().union(*attrs.values()))
    rng.shuffle(cols)
    hidden: set[str] = set()
    for c in cols:
        trial = hidden | {c}
        if sum(bool(a & trial) for a in attrs.values()) <= HIDDEN_SHARE * len(rows):
            hidden = trial
    build = sorted(q for q, a in attrs.items() if not a & hidden)
    held = sorted(q for q, a in attrs.items() if a & hidden)
    rng.shuffle(held)
    k = max(1, len(held) // 8)
    stable = [rng.choice(build) for _ in range(30)]
    for q in held[:k]:
        stable.insert(rng.randrange(len(stable) + 1), q)
    trend = []
    for q in held[k:]:
        trend += [q, rng.choice(build)]
    recur = [rng.choice(held) if rng.random() < 0.5 else rng.choice(build) for _ in range(20)]
    stream = [(q, "stable") for q in stable] + [(q, "trend") for q in trend] + [(q, "recur") for q in recur]
    return {"hidden": sorted(hidden), "build": build, "held": held, "stream": stream, "rows": rows}


class DryExecutor:
    """Accounts for reads without making them; pushdown is evaluated on the full protocol database (the
    values a patch or rebuild would approximately produce)."""

    def __init__(self, db: Path):
        self.db = db

    def pushdown(self, table, sql, known, single):
        cond = C.pushdown_conjuncts(sql, table, known) if single else None
        return C.evaluate_scope(self.db, table, cond) if cond else None

    def patch(self, *a) -> int:
        return 0

    def rebuild(self, *a) -> int:
        return 0


class RealExecutor:
    def __init__(self, spec, folder: Path, journal: Path, protocol_db: Path, hidden: list[str], all_queries: dict[str, str],
                 docs, caller, workers: int, stop_at: float | None):
        self.spec, self.folder, self.journal, self.docs = spec, folder, journal, docs
        self.caller, self.workers, self.stop_at, self.all_queries = caller, workers, stop_at, all_queries
        self.master = folder / "master.db"
        (folder / "versions").mkdir(parents=True, exist_ok=True)
        if not self.master.exists():
            shutil.copy2(protocol_db, self.master)
            conn = sqlite3.connect(self.master)
            with conn:
                for qa in hidden:
                    t, a = qa.split(".", 1)
                    try:
                        conn.execute(f'UPDATE "{t}" SET "{a}" = NULL')
                    except sqlite3.OperationalError:
                        pass
            self._complete(conn)
            conn.close()
            self.snapshot(0)

    def _complete(self, conn) -> None:
        from quwarts.core.schema_columns import complete_physical_schema
        from quwarts.core.signature import audit_workload, enumerate_predicates
        from quwarts.core.signature_realize import live_predicates

        audit = audit_workload([{"query_id": q, "sql": s} for q, s in self.all_queries.items()])
        complete_physical_schema(conn, self.all_queries, live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible)))
        conn.commit()

    def snapshot(self, version: int) -> None:
        shutil.copy2(self.master, self.folder / "versions" / f"v{version}.db")

    def pushdown(self, table, sql, known, single):
        cond = C.pushdown_conjuncts(sql, table, known) if single else None
        return C.evaluate_scope(self.master, table, cond) if cond else None

    def _left(self) -> float | None:
        if self.stop_at is None:
            return None
        left = self.stop_at - time.monotonic()
        if left < 5:
            raise Incomplete()
        return left

    def _by_sha(self) -> dict[str, dict]:
        out = {}
        for line in self.journal.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["prompt_sha"]] = row
        return out

    def _view(self, table_docs: dict[str, list[str]]):
        root = Path(tempfile.mkdtemp(prefix="quwarts_mat_"))
        tables = []
        from dataclasses import replace

        for t in self.spec.tables:
            d = root / t.sql_name
            d.mkdir()
            for name in table_docs.get(t.sql_name, []):
                (d / name).symlink_to(Path(self.docs[t.sql_name][name]).resolve())
            tables.append(replace(t, doc_dir=d))
        return replace(self.spec, tables=tuple(tables)), root

    def _read(self, view, reads, fields) -> int:
        from quwarts.core.router.executor import run_reads

        before = self.caller.ledger.spent
        stats = run_reads(view, reads, {}, fields, self.caller, self.journal, self.workers, long_documents="chain",
                          deadline=self._left())
        if stats.get("stopped_at_deadline") or stats.get("exhausted"):
            raise Incomplete()
        return self.caller.ledger.spent - before

    def patch(self, table, docs, specs, fields, seen) -> int:
        from quwarts.core.router.executor import commit_value

        read = C.Read(table, "patch:" + ",".join(f.name for f in specs), tuple(f.name for f in specs))
        view, root = self._view({table: docs})
        try:
            spent = self._read(view, [read], fields)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        values = C.read_values({table: {d: self.docs[table][d] for d in docs}}, [read], fields, self._by_sha())
        conn = sqlite3.connect(self.master)
        with conn:
            have = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            for f in specs:  # robust reads fill schema columns no query has referenced yet
                if f.name not in have:
                    kind = "REAL" if f.value_type in ("int", "float") else "TEXT"
                    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{f.name}" {kind}')
            ids = {C._doc_name(r[0]): r[0] for r in conn.execute(f'SELECT doc_id FROM "{table}"')}
            for d in docs:
                got = values.get((table, d))
                if got is None or d not in ids:
                    continue
                for f in specs:
                    conn.execute(f'UPDATE "{table}" SET "{f.name}" = ? WHERE doc_id = ?',
                                 (commit_value(got.get(f.name), fields[f"{table}.{f.name}"]), ids[d]))
        conn.close()
        return spent

    def rebuild(self, fields, reads, seen) -> int:
        from quwarts.eval.router_provenance import build

        spent = self._read(self.spec, reads, fields)
        values = C.read_values(self.docs, reads, fields, self._by_sha())
        grouped: dict = {}
        for (t, d), v in values.items():
            grouped.setdefault((t, C.SHARED), {})[d] = v
        tmp = self.folder / "rebuild.tmp.db"
        # The builder creates the columns its queries reference; a plain SELECT per table makes it create the
        # robust design's other columns too (no predicate, so the query path's rewriting is unchanged).
        columns = {f"__schema__:{r.table}": f'SELECT {", ".join(chr(34) + a + chr(34) for a in r.attributes)} FROM "{r.table}"'
                   for r in reads}
        build(self.spec, reads, grouped, fields, {**self.all_queries, **columns}, tmp)
        shutil.move(str(tmp), self.master)
        conn = sqlite3.connect(self.master)
        self._complete(conn)  # the query path's signature columns for the whole stream, as at the start
        conn.close()
        return spent


def run(corpus: str, policy: str, real: bool, deadline: float | None = None, workers: int = 24) -> dict[str, Any]:
    spec, train, test, run_dir, docs = context(corpus)
    s = make_stream(spec, train)
    rows = s["rows"]
    folder = ROOT / corpus / ("real" if real else "dry") / policy
    folder.mkdir(parents=True, exist_ok=True)
    (ROOT / corpus / "stream.json").write_text(json.dumps({k: v for k, v in s.items() if k != "rows"}, indent=1))
    names = {t: sorted(d) for t, d in docs.items()}
    costs = C.Costs(doc_tokens(corpus, docs))
    build_q = {q: rows[q] for q in s["build"]}
    if real:
        from quwarts.core.ledger import TokenLedger
        from quwarts.core.llm.openrouter import load_env_file, make_caller
        from quwarts.core.router.registry import PROJECT

        load_env_file(PROJECT / ".env")
        journal = ROOT / corpus / "reads.jsonl"
        if not journal.exists():
            shutil.copy2(run_dir / "reads.jsonl", journal)
        caller = make_caller(TokenLedger(theta=10**12), max_tokens=600)
        stop_at = None if deadline is None else time.monotonic() + deadline
        executor = RealExecutor(spec, folder, journal, run_dir / "read_first_blank.db", s["hidden"], rows, docs,
                                caller, workers, stop_at)
    else:
        executor = DryExecutor(run_dir / "read_first_blank.db")
    # "drift@0.25": trust parameter lambda (default 0.5); a "_observed" suffix: the non-robust ablation
    name, _, lam = policy.partition("@")
    base = name.removesuffix("_observed")
    m = C.Materializer(spec, build_q, names, costs, executor, base, trust=float(lam) if lam else 0.5,
                       robust=not name.endswith("_observed"))
    state_path = folder / "state.json"
    if state_path.exists():
        m.load_state(json.loads(state_path.read_text()))
    status = "complete"
    for qid, _phase in s["stream"][len(m.steps):]:
        try:
            st = m.step(qid, rows[qid])
        except Incomplete:
            status = "incomplete"
            break
        if real and st.action != "answer":
            executor.snapshot(st.version)
        state_path.write_text(json.dumps(m.to_state(), default=list))
    return summarize(corpus, policy, real, s, m) | {"status": status}


def summarize(corpus, policy, real, s, m) -> dict[str, Any]:
    phases = [p for _q, p in s["stream"]]
    out = {"corpus": corpus, "policy": policy, "steps": len(m.steps), "queries": len(s["stream"]),
           "hidden": s["hidden"], "build_queries": len(s["build"]), "held_queries": len(s["held"])}
    tok = {"patch": 0, "rebuild": 0}
    for st in m.steps:
        if st.action == "patch":
            tok["patch"] += st.patch_tokens
        elif st.action == "rebuild":
            tok["rebuild"] += st.rebuild_tokens
    out.update({"cost_tokens": tok["patch"] + tok["rebuild"], "patch_tokens": tok["patch"], "rebuild_tokens": tok["rebuild"],
                "patches": sum(st.action == "patch" for st in m.steps), "rebuilds": sum(st.action == "rebuild" for st in m.steps),
                "spent": sum(st.spent for st in m.steps),
                "actions": [f"{st.pos}:{phases[st.pos]}:{st.action}" for st in m.steps if st.action != "answer"],
                "drift_p": [(st.pos, st.drift.get("p")) for st in m.steps if st.drift]})
    return out


def offline(corpus: str) -> dict[str, Any]:
    """Clairvoyant single-rebuild optimum: patch until step t (the patch-only costs), then one rebuild whose
    design already covers every query of the stream; or never rebuild."""

    spec, train, test, run_dir, docs = context(corpus)
    s = make_stream(spec, train)
    rows = s["rows"]
    costs = C.Costs(doc_tokens(corpus, docs))
    fields, reads = C.design(spec, {**{q: rows[q] for q in s["build"]}, **{q: rows[q] for q, _p in s["stream"]}})
    full = sum(costs.reads(r.table, sorted(docs[r.table]), [fields[f"{r.table}.{a}"] for a in r.attributes])
               for r in reads if r.table in docs)
    prefix = min(sum(st["patch_tokens"] for st in json.loads((ROOT / corpus / "dry" / p / "state.json").read_text())["steps"]
                     if st["action"] == "patch") for p in ("patch", "patch_observed"))
    # Rebuilding after some patches never beats rebuilding first (its design covers the whole stream),
    # so the clairvoyant optimum is the cheaper of never rebuilding (the cheaper patching) and rebuilding
    # before the first query with the design of the whole stream.
    best = min(prefix, full)
    return {"patch_only": prefix, "rebuild_first": full, "offline_optimum": best}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--dry", action="store_true")
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--policy", default="drift", help="patch | eager | onlinept | drift[@lambda] | drift_observed")
    parser.add_argument("--deadline", type=float, default=None)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args(argv)
    if args.dry:
        report = {}
        for policy in [*C.POLICIES, "drift@0.25", *(f"{p}_observed" for p in C.POLICIES)]:
            state = ROOT / args.corpus / "dry" / policy / "state.json"
            if state.exists():
                state.unlink()
            report[policy] = run(args.corpus, policy, False)
        report["offline"] = offline(args.corpus)
        (ROOT / args.corpus / "dry_report.json").write_text(json.dumps(report, indent=1))
        for p, r in report.items():
            print(p, json.dumps({k: v for k, v in r.items() if k not in ("drift_p", "hidden")})[:600])
    if args.real:
        print(json.dumps(run(args.corpus, args.policy, True, args.deadline, args.workers))[:1500])
    if args.score:
        print(json.dumps(score(args.corpus), indent=1)[:4000])
    return 0


def score(corpus: str) -> dict[str, Any]:
    from quwarts.eval.router_execute_v3 import DATASET, score as score_db

    spec, train, test, run_dir, docs = context(corpus)
    s = make_stream(spec, train)
    rows = s["rows"]
    out = {}
    for folder in sorted((ROOT / corpus / "real").glob("*")):
        state = json.loads((folder / "state.json").read_text())
        steps = state["steps"]
        cache: dict[int, dict[str, float]] = {}
        per_pos = []
        for st in steps:
            v = st["version"]
            if v not in cache:
                db = folder / "versions" / f"v{v}.db"
                res = score_db(DATASET[spec.name], rows, {q: str(db) for q in rows}, db)
                cache[v] = {r["query_id"]: float(r["product"]) for r in res["per_query"]}
            per_pos.append(cache[v].get(st["qid"], 0.0))
        phases = [p for _q, p in s["stream"]][: len(steps)]
        held = set(s["held"])
        pick = lambda f: [x for x, st, ph in zip(per_pos, steps, phases) if f(st, ph)]  # noqa: E731
        mean = lambda xs: round(sum(xs) / len(xs), 4) if xs else None  # noqa: E731
        out[folder.name] = {"steps": len(steps), "mean_product": mean(per_pos),
                            "hidden_column_queries": mean(pick(lambda st, ph: st["qid"] in held)),
                            "build_queries": mean(pick(lambda st, ph: st["qid"] not in held)),
                            "spent": sum(st["spent"] for st in steps)}
    (ROOT / corpus / "real_score.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    sys.exit(main())

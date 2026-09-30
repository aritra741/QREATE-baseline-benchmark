"""Drift experiments on the design of ``drift_design`` (QuWARTS only). AUDIT for scores: reads gold.

    python -m quwarts.eval.drift_run --corpus cspaper --estimate               # build-read costs (no calls)
    python -m quwarts.eval.drift_run --corpus cspaper --read --deadline 120    # the W0-informed robust read
    python -m quwarts.eval.drift_run --corpus cspaper --raw                    # read values -> raw databases
    python -m quwarts.eval.drift_run --corpus cspaper --replay --deadline 150  # every policy on every stream
    python -m quwarts.eval.drift_run --report

The build read. One read per corpus is the system's own build read: informed by W0 alone (usage phrases
for W0's columns only, no phrase from any test or drift query) and robust (every schema column of every
table the query pool reads; chained reads for long documents). Every policy is replayed from it:

* ``static``   lean build (W0's attributes), no adaptation, representation frozen at W0's literals
* ``quwarts``  lean build, the drift controller (answer / patch / rebuild: ski rental with the drift
               prediction) and online representation (an arriving query's literals join the workload
               before it is answered; its answer never does)
* ``robust``   prefetch every schema column at build time, online representation
* ablations    ``frozen_rep`` (the controller with the representation frozen at W0), ``whole_rep`` (the
               representation from W0 and the whole stream: a look-ahead upper bound), ``raw`` (no
               representation), ``static_raw`` (the static build without representation); controller
               policies ``patch``, ``onlinept``, ``eager``, ``drift`` and the non-robust ``drift_observed``
               (cost only); ``clairvoyant``: a lean build with the design of W0 and the whole stream.

Replay equivalence. A patch reads the missing columns for the documents that can affect the query's
answer: the WHERE conjuncts over complete columns are evaluated on the served view, and documents they
exclude are filtered out whatever the new column holds. The answer therefore equals the answer on a
database where every document has the column, and every adaptive policy answers each query from the
same values: policies differ in cost and in representation, and the static policy in missing columns.
The approximations, shared by all policies: a lean or patch prompt lists fewer fields than the robust
read, and a patched column gets no usage phrase (its real read would have one); a rebuild re-reads with
the robust W0 design. Costs are the controller's token estimates for every read a policy decides on.

Scores. A query's score is a function of the query and the contents of the columns it references, so
scores are memoized by (query, digest of those columns): a view that leaves a query's columns unchanged
is not scored again. Signature predicates are computed once over the whole query catalog, and every
database is completed with them (the chunked-scoring artifact cannot arise).
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import json
import os
import random
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from quwarts.core.adapt import controller as C
from quwarts.core.router.registry import RESULTS

ROOT = RESULTS / "drift_design"  # build workloads, build reads and the audit
# Streams, runs and reports: ``drift_design`` (pooled streams) or ``drift_paired`` (template-paired streams,
# ``eval/drift_paired.py``), chosen with QUWARTS_DRIFT_DESIGN.
DESIGN = os.environ.get("QUWARTS_DRIFT_DESIGN", "drift_design")
DROOT = RESULTS / DESIGN
SCRATCH = Path.home() / "quwarts_scratch" / ("drift_run" if DESIGN == "drift_design" else f"drift_run_{DESIGN}")
CORPORA = ["cspaper", "player", "art", "med", "legal", "finan"]
SEEDS = (0, 1, 2)
COST_POLICIES = ["patch", "onlinept", "eager", "drift", "drift_observed"]
FIXED = ["lean_raw", "lean_frozen", "robust_raw", "robust_frozen"]


# ------------------------------------------------------------------------------------------ speed

def _memoize_table_attributes() -> None:
    """``workload_features.sql_table_attributes`` with each statement's contribution memoized. The
    controller calls it on its whole context at every step; a statement's contribution does not depend
    on the other statements, so the memoized union is exactly the original result."""

    import sqlglot
    from sqlglot import exp
    from quwarts.core.router import workload_features as WF

    if getattr(WF.sql_table_attributes, "memoized", False):
        return

    @functools.lru_cache(maxsize=None)
    def one(sql: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
        tree = sqlglot.parse_one(sql, read="sqlite")
        aliases = WF.alias_map(tree)
        names = set(aliases.values())
        output_aliases = {n.alias for n in tree.find_all(exp.Alias) if n.alias}
        found: dict[str, set[str]] = {}
        for column in tree.find_all(exp.Column):
            if not column.name or (not column.table and column.name in output_aliases):
                continue
            if column.table:
                table = aliases.get(column.table)
                if table:
                    found.setdefault(table, set()).add(column.name)
            elif len(names) == 1:
                found.setdefault(next(iter(names)), set()).add(column.name)
        return tuple((k, tuple(sorted(v))) for k, v in found.items())

    def sql_table_attributes(queries, tables):
        out = {t: set() for t in tables}
        for sql in queries.values():
            for table, cols in one(sql):
                out.setdefault(table, set()).update(cols)
        return out

    sql_table_attributes.memoized = True
    WF.sql_table_attributes = sql_table_attributes


# ------------------------------------------------------------------------------------------ context

def w0_design(spec, w0: dict[str, str], tables: set[str]):
    """The robust W0 design (``controller.design``) extended to every table the pool reads."""

    from quwarts.core.router.context_probe import protocol_field_specs
    from quwarts.core.router.needs import Need

    fields, reads = C.design(spec, w0, robust=True)
    extra = sorted(set(tables) - {r.table for r in reads})
    if extra:
        schema = spec.benchmark_attribute_descriptions(purpose="protocol")
        needs = [Need("__schema__", t, a, "value") for t in extra for a in sorted(schema.get(spec.table(t).attributes_key, {}))]
        fields = {**fields, **protocol_field_specs(spec, needs)}
        reads = sorted(reads + [C.Read(t, C.SHARED, tuple(sorted({n.attribute for n in needs if n.table == t}))) for t in extra],
                       key=lambda r: r.table)
    return fields, reads


@functools.lru_cache(maxsize=None)
def context(corpus: str) -> SimpleNamespace:
    from quwarts.eval import materialize_stream as MS

    _memoize_table_attributes()
    spec, _train, _test, _run, docs = MS.context(corpus)
    w0 = dict(json.loads((ROOT / corpus / "build.json").read_text())["build"])
    designs = {s: json.loads((DROOT / corpus / f"design_seed{s}.json").read_text()) for s in SEEDS}
    records: dict[str, dict] = {}
    for d in designs.values():
        records.update(d["queries"])
    catalog = {q: r["sql"] for q, r in records.items()}
    fields, reads = w0_design(spec, w0, {t for r in records.values() for t in r["attributes"]})
    lean_fields, lean_reads = C.design(spec, w0)
    costs = C.Costs(MS.doc_tokens(corpus, docs))
    names = {t: sorted(d) for t, d in docs.items()}
    return SimpleNamespace(corpus=corpus, spec=spec, docs=docs, names=names, w0=w0, designs=designs, records=records,
                           catalog=catalog, fields=fields, reads=reads, lean_fields=lean_fields, lean_reads=lean_reads,
                           costs=costs, folder=DROOT / corpus / "run", scratch=SCRATCH / corpus)


def read_cost(ctx, fields, reads) -> int:
    return sum(ctx.costs.reads(r.table, ctx.names[r.table], [fields[f"{r.table}.{a}"] for a in r.attributes])
               for r in reads if r.table in ctx.names)


def estimate(corpus: str) -> dict[str, Any]:
    ctx = context(corpus)
    return {"corpus": corpus, "robust_build_tokens": read_cost(ctx, ctx.fields, ctx.reads),
            "lean_build_tokens": read_cost(ctx, ctx.lean_fields, ctx.lean_reads),
            "robust_fields": {r.table: len(r.attributes) for r in ctx.reads},
            "lean_fields": {r.table: len(r.attributes) for r in ctx.lean_reads},
            "documents": {t: len(d) for t, d in ctx.names.items()}}


# ------------------------------------------------------------------------------------------ the read

def journal(corpus: str) -> Path:
    return ROOT / corpus / "reads.jsonl"


def read(corpus: str, deadline: float, workers: int) -> dict[str, Any]:
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.router.executor import run_reads
    from quwarts.core.router.registry import PROJECT

    ctx = context(corpus)
    load_env_file(PROJECT / ".env")
    caller = make_caller(TokenLedger(theta=10**12), max_tokens=700)
    stats = run_reads(ctx.spec, ctx.reads, {}, ctx.fields, caller, journal(corpus), workers, long_documents="chain",
                      deadline=deadline)
    stats["spent_this_run"] = caller.ledger.spent
    return stats


def journal_rows(corpus: str) -> dict[str, dict]:
    out = {}
    path = journal(corpus)
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                out[row["prompt_sha"]] = row
    return out


# ------------------------------------------------------------------------------------------ databases

@functools.lru_cache(maxsize=None)
def predicates(corpus: str):
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates

    ctx = context(corpus)
    audit = audit_workload([{"query_id": q, "sql": s} for q, s in ctx.catalog.items()])
    return live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))


def complete(corpus: str, db: Path) -> None:
    from quwarts.core.schema_columns import complete_physical_schema

    conn = sqlite3.connect(db)
    complete_physical_schema(conn, context(corpus).catalog, predicates(corpus))
    conn.commit()
    conn.close()


def fixed_db(corpus: str, name: str) -> Path:
    return context(corpus).scratch / f"{name}.db"


def raw(corpus: str) -> dict[str, Any]:
    """The robust raw database from the read, the lean raw database (W0's attributes; every other read
    column NULL), and each with the representation frozen at W0's literals."""

    from quwarts.core.represent import Config, build
    from quwarts.eval.router_provenance import build as builder

    ctx = context(corpus)
    ctx.scratch.mkdir(parents=True, exist_ok=True)
    ctx.folder.mkdir(parents=True, exist_ok=True)
    rows = journal_rows(corpus)
    values = C.read_values(ctx.docs, ctx.reads, ctx.fields, rows)
    read_tables = {r.table for r in ctx.reads}
    missing = sorted(f"{t}/{d}" for t in read_tables for d in ctx.names[t] if (t, d) not in values)
    grouped: dict = {}
    for (t, d), v in values.items():
        grouped.setdefault((t, C.SHARED), {})[d] = v
    columns = {f"__schema__:{r.table}": f'SELECT {", ".join(chr(34) + a + chr(34) for a in r.attributes)} FROM "{r.table}"'
               for r in ctx.reads}
    robust = fixed_db(corpus, "robust_raw")
    tmp = robust.with_suffix(".tmp.db")
    builder(ctx.spec, ctx.reads, grouped, ctx.fields, {**ctx.catalog, **columns}, tmp)
    complete(corpus, tmp)
    shutil.move(str(tmp), robust)
    lean = fixed_db(corpus, "lean_raw")
    shutil.copy2(robust, lean)
    keep = {(r.table, a) for r in ctx.lean_reads for a in r.attributes}
    nulled = []
    conn = sqlite3.connect(lean)
    with conn:
        for r in ctx.reads:
            for a in r.attributes:
                if (r.table, a) not in keep:
                    try:
                        conn.execute(f'UPDATE "{r.table}" SET "{a}" = NULL')
                        nulled.append(f"{r.table}.{a}")
                    except sqlite3.OperationalError:
                        pass
    conn.close()
    for base in ("lean", "robust"):
        build(fixed_db(corpus, f"{base}_raw"), fixed_db(corpus, f"{base}_frozen"), ctx.spec, ctx.fields, ctx.w0, Config())
    spent = sum(r.get("tokens", 0) for r in rows.values())
    out = {"corpus": corpus, "documents_read": len(values), "documents_missing": missing, "nulled_in_lean": nulled,
           "journal_calls": len(rows), "journal_tokens": spent, "estimate": estimate(corpus)}
    (ctx.folder / "raw.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------------------------------ scores

def referenced(sql: str) -> tuple[set[str], set[str]]:
    import sqlglot
    from sqlglot import exp

    tree = sqlglot.parse_one(sql, read="sqlite")
    return {t.name for t in tree.find_all(exp.Table)}, {c.name.lower() for c in tree.find_all(exp.Column)}


def digest(db: Path, sql: str) -> str:
    """The contents of the columns a query references (and each table's row count)."""

    tables, cols = referenced(sql)
    h = hashlib.sha256()
    conn = sqlite3.connect(db)
    try:
        for t in sorted(tables):
            have = [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')]
            use = [c for c in have if c.lower() in cols or c.lower().removesuffix("__canonical") in cols]
            sel = ", ".join(f'"{c}"' for c in use) or "1"
            h.update(f"{t}|{use}".encode())
            h.update(repr(conn.execute(f'SELECT {sel} FROM "{t}" ORDER BY rowid').fetchall()).encode())
    finally:
        conn.close()
    return h.hexdigest()[:16]


class Scorer:
    """Benchmark and tolerant scores, memoized by (query, digest) in ``run/scores.json``."""

    CHUNK = 8

    def __init__(self, corpus: str):
        self.corpus, self.ctx = corpus, context(corpus)
        self.path = self.ctx.folder / "scores.json"
        self.cache = json.loads(self.path.read_text()) if self.path.exists() else {"benchmark": {}, "tolerant": {}}
        self._gold = None

    def save(self) -> None:
        self.path.write_text(json.dumps(self.cache))

    def has(self, qid: str, dig: str) -> bool:
        k = f"{qid}|{dig}"
        return k in self.cache["benchmark"] and k in self.cache["tolerant"]

    def get(self, metric: str, qid: str, dig: str) -> float | None:
        return self.cache[metric].get(f"{qid}|{dig}")

    def gold(self):
        if self._gold is None:
            from diagnostics.run_config_grid import load_ground_truth
            from quwarts.eval.router_execute_v3 import DATASET
            from quwarts.eval.tolerant_score import cell
            from quwarts.experiments.synthesize_case80 import gold_name

            g = load_ground_truth(gold_name(DATASET[self.ctx.spec.name]))
            self._gold = (g, {t: [{k: cell(v) for k, v in r.items()} for r in rs] for t, rs in g.items()})
        return self._gold

    def run(self, items: list[tuple[str, str, Path]], stop) -> bool:
        """Score every (query, digest, database) not yet cached; False if stopped by the deadline."""

        for metric in ("benchmark", "tolerant"):
            todo, seen = [], set()
            for qid, dig, db in items:
                k = f"{qid}|{dig}"
                if k not in self.cache[metric] and k not in seen:
                    seen.add(k)
                    todo.append((qid, dig, db))
            for i in range(0, len(todo), self.CHUNK):
                if stop():
                    self.save()
                    return False
                self.cache[metric].update(self._score(metric, todo[i:i + self.CHUNK]))
                self.save()
        return True

    def _score(self, metric: str, chunk) -> dict[str, float]:
        from quwarts.core.pipeline import official_sql
        from quwarts.eval.router_execute_v3 import DATASET
        from quwarts.eval.tolerant_score import normalize_sql, normalized_copy
        from quwarts.experiments.synthesize_case80 import score_with_rewrites

        gold, gold_tol = self.gold()
        dataset = DATASET[self.ctx.spec.name]
        keys = {f"{q}|{d}": (q, db) for q, d, db in chunk}
        rows = [{"query_id": k, "sql": self.ctx.catalog[q], "pack": q.split(":", 1)[0]} for k, (q, _db) in keys.items()]
        tmp = None
        if metric == "benchmark":
            rewrites = {k: {"sql": official_sql(self.ctx.catalog[q], str(db), predicates(self.corpus), query_id=k), "sqlite_path": str(db)}
                        for k, (q, db) in keys.items()}
            base, g = Path(chunk[0][2]), gold
        else:
            tmp = self.ctx.scratch / "tol"
            copies, needed = {}, {}
            for q, db in keys.values():
                needed.setdefault(str(db), set()).update(referenced(self.ctx.catalog[q])[1])
            for db, cols in needed.items():
                copies[db] = str(normalized_copy(db, tmp / f"{len(copies):03d}_{Path(db).name}", cols))
            rows = [{**r, "sql": normalize_sql(r["sql"])} for r in rows]
            rewrites = {r["query_id"]: {"sql": r["sql"], "sqlite_path": copies[str(keys[r["query_id"]][1])]} for r in rows}
            base, g = Path(next(iter(copies.values()))), gold_tol
        report = score_with_rewrites(rows, rewrites, base, g, dataset)
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
        got = {r["query_id"]: round(float(r.get("structure_f2") or 0.0) * float(r.get("cell_f1_20") or 0.0), 4)
               for r in report.get("per_query") or []}
        return {k: got.get(k, 0.0) for k in keys}


# ------------------------------------------------------------------------------------------ replay

class ReplayExecutor:
    """No reads (the replay's values come from the build read); pushdown on the served view."""

    def __init__(self, db: Path):
        self.db = db

    def pushdown(self, table, sql, known, single):
        cond = C.pushdown_conjuncts(sql, table, known) if single else None
        return C.evaluate_scope(self.db, table, cond) if cond else None

    def patch(self, *a) -> int:
        return 0

    def rebuild(self, *a) -> int:
        return 0


class LazyViewExecutor(ReplayExecutor):
    """Pushdown on the online view of the current position, built only when a miss needs it."""

    def __init__(self, make):
        super().__init__(None)
        self.make = make

    def pushdown(self, table, sql, known, single):
        cond = C.pushdown_conjuncts(sql, table, known) if single else None
        return C.evaluate_scope(self.make(), table, cond) if cond else None


def robust_materializer(ctx, executor) -> "C.Materializer":
    """The controller started from the robust build: every column of the robust read is complete."""

    m = C.Materializer(ctx.spec, ctx.w0, ctx.names, ctx.costs, executor, "drift")
    m.fields, m.reads = ctx.fields, ctx.reads
    m.materialized = {(r.table, a): set(ctx.names[r.table]) for r in ctx.reads for a in r.attributes}
    return m


def action(st) -> list:
    return [st.action, st.patch_tokens if st.action == "patch" else 0, st.rebuild_tokens if st.action == "rebuild" else 0,
            st.scope_docs, st.drift.get("p") if st.drift else None]


def add_robust(corpus: str, sim: dict[str, Any]) -> dict[str, Any]:
    """The robust-start controller on a stream simulated before it existed (online views built lazily)."""

    from quwarts.core.represent import Config, build

    ctx = context(corpus)
    stream = [p["qid"] for p in sim["positions"]]
    tmp = ctx.scratch / "views" / "lazy.db"
    state = {"workload": dict(ctx.w0), "built": None}

    def make():
        if state["built"] != len(state["workload"]):
            build(fixed_db(corpus, "robust_raw"), tmp, ctx.spec, ctx.fields, state["workload"], Config())
            state["built"] = len(state["workload"])
        return tmp

    m = robust_materializer(ctx, LazyViewExecutor(make))
    for p, q in zip(sim["positions"], stream):
        state["workload"][q] = ctx.catalog[q]
        p["actions"]["robust"] = action(m.step(q, ctx.catalog[q]))
    return sim


def fixed_digests(corpus: str) -> dict[str, dict[str, str]]:
    ctx = context(corpus)
    path = ctx.folder / "fixed_digests.json"
    if path.exists():
        return json.loads(path.read_text())
    out = {name: {q: digest(fixed_db(corpus, name), s) for q, s in ctx.catalog.items() if q not in ctx.w0} for name in FIXED}
    path.write_text(json.dumps(out))
    return out


def stream_keys(corpus: str) -> list[tuple[int, str]]:
    ctx = context(corpus)
    return [(s, k) for s in SEEDS for k in ctx.designs[s]["streams"]]


def sim_path(corpus: str, seed: int, key: str) -> Path:
    return context(corpus).folder / f"seed{seed}" / f"{key.replace('/', '_')}.sim.json"


def simulate(corpus: str, seed: int, key: str) -> dict[str, Any]:
    """Online views and the controller policies on one stream (no scoring)."""

    from quwarts.core.represent import Config, build

    ctx = context(corpus)
    design = ctx.designs[seed]
    stream = design["streams"][key]
    t0 = set(design["in_distribution"])
    views = ctx.scratch / "views" / f"s{seed}_{key.replace('/', '_')}"
    views.mkdir(parents=True, exist_ok=True)
    robust = fixed_db(corpus, "robust_raw")
    online = ReplayExecutor(robust)
    frozen = ReplayExecutor(fixed_db(corpus, "robust_frozen"))
    runs = {p: C.Materializer(ctx.spec, ctx.w0, ctx.names, ctx.costs, online, p.removesuffix("_observed"),
                              robust=not p.endswith("_observed")) for p in COST_POLICIES}
    runs["frozen_rep"] = C.Materializer(ctx.spec, ctx.w0, ctx.names, ctx.costs, frozen, "drift")
    runs["robust"] = robust_materializer(ctx, online)
    whole = views / "whole.db"
    build(robust, whole, ctx.spec, ctx.fields, {**ctx.w0, **{q: ctx.catalog[q] for q in stream}}, Config())
    positions = []
    workload = dict(ctx.w0)
    for t, q in enumerate(stream):
        sql = ctx.catalog[q]
        workload[q] = sql
        view = views / f"{t:02d}.db"
        manifest = build(robust, view, ctx.spec, ctx.fields, workload, Config())
        online.db = view
        acts = {}
        for p, m in runs.items():
            acts[p] = action(m.step(q, sql))
        dig = digest(view, sql)
        positions.append({"pos": t, "qid": q, "drift": q not in t0, "online": dig, "online_db": str(view),
                          "whole": digest(whole, sql), "actions": acts, "view_changes": manifest.get("cells_changed")})
    out = {"corpus": corpus, "seed": seed, "stream": key, "positions": positions, "whole_db": str(whole),
           "tokens": {"lean_build": read_cost(ctx, ctx.lean_fields, ctx.lean_reads), "robust_build": read_cost(ctx, ctx.fields, ctx.reads),
                      "clairvoyant_build": read_cost(ctx, *C.design(ctx.spec, {**ctx.w0, **{q: ctx.catalog[q] for q in stream}}))}}
    return out


def replay(corpus: str, deadline: float | None) -> dict[str, Any]:
    ctx = context(corpus)
    start = time.monotonic()
    stop = (lambda: False) if deadline is None else (lambda: time.monotonic() - start > deadline)
    scorer = Scorer(corpus)
    fixed = fixed_digests(corpus)
    items = [(q, d, fixed_db(corpus, name)) for name, ds in fixed.items() for q, d in ds.items()]
    if not scorer.run(items, stop):
        return {"status": "scoring fixed databases", "scored": len(scorer.cache["tolerant"])}
    done = 0
    for seed, key in stream_keys(corpus):
        path = sim_path(corpus, seed, key)
        if path.exists():
            sim = json.loads(path.read_text())
            if "robust" not in sim["positions"][0]["actions"]:
                if deadline is not None and deadline - (time.monotonic() - start) < 20:
                    return {"status": "stopped", "streams_done": done}
                sim = add_robust(corpus, sim)
                path.write_text(json.dumps(sim))
            if sim.get("scored"):
                done += 1
                continue
        else:
            if deadline is not None and deadline - (time.monotonic() - start) < 60:
                return {"status": "stopped", "streams_done": done}
            sim = simulate(corpus, seed, key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(sim))
        pending = [(p["qid"], p["online"], Path(p["online_db"])) for p in sim["positions"]]
        pending += [(p["qid"], p["whole"], Path(sim["whole_db"])) for p in sim["positions"]]
        pending = [x for x in pending if not scorer.has(x[0], x[1])]
        lost = [x for x in pending if not x[2].exists()]
        if lost:  # the scratch views are gone (a new session): simulate again
            path.unlink()
            return {"status": f"views lost for {seed}/{key}; rerun", "streams_done": done}
        if not scorer.run(pending, stop):
            return {"status": "stopped while scoring", "streams_done": done}
        sim["scored"] = True
        path.write_text(json.dumps(sim))
        shutil.rmtree(Path(sim["whole_db"]).parent, ignore_errors=True)
        done += 1
    return {"status": "complete", "streams_done": done, "elapsed": round(time.monotonic() - start, 1)}


# ------------------------------------------------------------------------------------------ report

LEVELS = ["0", "25", "50", "75", "100"]
AXES = ["attribute", "value", "combined"]
ACCURACY = {"static": "lean_frozen", "static_raw": "lean_raw", "frozen_rep": "robust_frozen", "raw": "robust_raw"}


def results(corpus: str) -> dict[tuple[int, str], dict[str, Any]]:
    """Per stream: per-position scores of every policy (both metrics) and its tokens."""

    ctx = context(corpus)
    path = ctx.folder / "scores.json"
    if not path.exists():
        return {}
    scores = json.loads(path.read_text())
    fixed = fixed_digests(corpus)
    out = {}
    for seed, key in stream_keys(corpus):
        sp = sim_path(corpus, seed, key)
        if not sp.exists():
            continue
        sim = json.loads(sp.read_text())
        if not sim.get("scored"):
            continue
        P = sim["positions"]
        acc: dict[str, dict[str, list]] = {}
        for metric in ("benchmark", "tolerant"):
            s = scores[metric]
            acc.setdefault("quwarts", {})[metric] = [s[f"{p['qid']}|{p['online']}"] for p in P]
            acc.setdefault("whole_rep", {})[metric] = [s[f"{p['qid']}|{p['whole']}"] for p in P]
            for name, db in ACCURACY.items():
                acc.setdefault(name, {})[metric] = [s[f"{p['qid']}|{fixed[db][p['qid']]}"] for p in P]
        acc["robust"] = acc["quwarts"]  # the same values under replay (module docstring)
        tok = sim["tokens"]
        adapt = {pol: sum(p["actions"][pol][1] + p["actions"][pol][2] for p in P) for pol in P[0]["actions"]}
        adapt.pop("robust", None) if "robust" not in P[-1]["actions"] else None
        tokens = {"static": tok["lean_build"], "quwarts": tok["lean_build"] + adapt["drift"],
                  "robust": tok["robust_build"] + adapt.get("robust", 0),
                  "clairvoyant": tok["clairvoyant_build"], **{f"policy:{pol}": tok["lean_build"] + v for pol, v in adapt.items()}}
        actions = {pol: [f"{p['pos']}:{p['actions'][pol][0]}" for p in P if p["actions"][pol][0] != "answer"] for pol in P[0]["actions"]}
        out[(seed, key)] = {"acc": acc, "tokens": tokens, "actions": actions, "drift": [p["drift"] for p in P], "n": len(P)}
    return out


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def paired(res, keys, a: str, b: str, metric: str):
    from quwarts.eval.represent_eval import paired_ci

    diffs = [x - y for k in keys if k in res for x, y in zip(res[k]["acc"][a][metric], res[k]["acc"][b][metric])]
    return mean(diffs), paired_ci(diffs) if len(diffs) > 2 else [float("nan")] * 2


def cell_acc(res, axis: str, level: str, policy: str, metric: str) -> float:
    keys = [(s, f"{axis}/{level}") for s in SEEDS]
    return mean([x for k in keys if k in res for x in res[k]["acc"][policy][metric]])


def cell_tokens(res, axis: str, level: str, policy: str) -> float:
    return mean([res[(s, f"{axis}/{level}")]["tokens"][policy] for s in SEEDS if (s, f"{axis}/{level}") in res])


def complete_count(res) -> str:
    return f"{len(res)}/{len(SEEDS) * 18}"


def report() -> str:
    lines = ["# Drift experiments: results (generated by `eval/drift_run.py --report`)", ""]
    allres = {c: results(c) for c in CORPORA}
    lines += ["Streams scored: " + ", ".join(f"{c} {complete_count(r)}" for c, r in allres.items()), ""]
    for metric in ("benchmark", "tolerant"):
        lines += [f"## Accuracy, {metric} metric: static / adaptive (mean of 3 seeds x 28 queries)", "",
                  "Adaptive: the controller with online representation; the lean and the robust build answer from the same values under replay.", "",
                  "| Corpus | Axis | " + " | ".join(f"{l}%" for l in LEVELS) + " | adaptive - static at 100% [95% CI] |",
                  "|---|---|" + "---:|" * len(LEVELS) + "---|"]
        for c, res in allres.items():
            for axis in AXES:
                if not any((s, f"{axis}/0") in res for s in SEEDS):
                    continue
                cells = [f"{cell_acc(res, axis, l, 'static', metric):.3f} / {cell_acc(res, axis, l, 'quwarts', metric):.3f}" for l in LEVELS]
                d, ci = paired(res, [(s, f"{axis}/100") for s in SEEDS], "quwarts", "static", metric)
                lines.append(f"| {c} | {axis} | " + " | ".join(cells) + f" | {d:+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}] |")
        lines.append("")
    lines += ["## Tokens (millions, mean of 3 seeds): static / lean build + controller / robust build + controller / clairvoyant lean build", "",
              "| Corpus | Axis | " + " | ".join(f"{l}%" for l in LEVELS) + " | gradual |", "|---|---|" + "---:|" * (len(LEVELS) + 1)]
    for c, res in allres.items():
        for axis in AXES:
            if not any((s, f"{axis}/0") in res for s in SEEDS):
                continue
            cells = []
            for l in LEVELS + ["gradual"]:
                v = [cell_tokens(res, axis, l, p) / 1e6 for p in ("static", "quwarts", "robust", "clairvoyant")]
                cells.append(" / ".join(f"{x:.2f}" for x in v))
            lines.append(f"| {c} | {axis} | " + " | ".join(cells) + " |")
    lines += ["", "## Representation under drift, benchmark metric: frozen at W0 / online / W0 + whole stream / none", "",
              "| Corpus | Axis | " + " | ".join(f"{l}%" for l in LEVELS) + " | online - frozen at 100% [95% CI] | online - none at 100% [95% CI] |",
              "|---|---|" + "---:|" * len(LEVELS) + "---|---|"]
    for c, res in allres.items():
        for axis in AXES:
            if not any((s, f"{axis}/0") in res for s in SEEDS):
                continue
            cells = [" / ".join(f"{cell_acc(res, axis, l, p, 'benchmark'):.3f}" for p in ("frozen_rep", "quwarts", "whole_rep", "raw")) for l in LEVELS]
            keys = [(s, f"{axis}/100") for s in SEEDS]
            d1, c1 = paired(res, keys, "quwarts", "frozen_rep", "benchmark")
            d2, c2 = paired(res, keys, "quwarts", "raw", "benchmark")
            lines.append(f"| {c} | {axis} | " + " | ".join(cells) + f" | {d1:+.3f} [{c1[0]:+.3f}, {c1[1]:+.3f}] | {d2:+.3f} [{c2[0]:+.3f}, {c2[1]:+.3f}] |")
    lines += ["", "## Controller policies: tokens (millions) at 100% and on the gradual stream, mean of 3 seeds", "",
              "| Corpus | Axis | Stream | lean: patch only | lean: OnlinePT | lean: eager rebuild | lean: drift (ski rental + prediction) | lean: drift, non-robust patches | robust build + drift controller | clairvoyant |",
              "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for c, res in allres.items():
        for axis in AXES:
            for l in ("100", "gradual"):
                if not any((s, f"{axis}/{l}") in res for s in SEEDS):
                    continue
                v = [cell_tokens(res, axis, l, p) / 1e6 for p in ("policy:patch", "policy:onlinept", "policy:eager", "policy:drift",
                                                                   "policy:drift_observed", "robust", "clairvoyant")]
                lines.append(f"| {c} | {axis} | {l} | " + " | ".join(f"{x:.2f}" for x in v) + " |")
    lines += ["", "## Gradual streams (drift probability rising 0 -> 1): benchmark accuracy by quarter, static / adaptive", "",
              "| Corpus | Axis | Q1 | Q2 | Q3 | Q4 | lean-build controller actions (seed 0) |", "|---|---|---:|---:|---:|---:|---|"]
    for c, res in allres.items():
        for axis in AXES:
            keys = [(s, f"{axis}/gradual") for s in SEEDS if (s, f"{axis}/gradual") in res]
            if not keys:
                continue
            cells = []
            for qtr in range(4):
                sl = lambda xs: xs[qtr * 14:(qtr + 1) * 14]  # noqa: E731
                a = mean([x for k in keys for x in sl(res[k]["acc"]["static"]["benchmark"])])
                b = mean([x for k in keys for x in sl(res[k]["acc"]["quwarts"]["benchmark"])])
                cells.append(f"{a:.3f} / {b:.3f}")
            acts = ", ".join(res[keys[0]]["actions"]["drift"]) or "none"
            lines.append(f"| {c} | {axis} | " + " | ".join(cells) + f" | {acts} |")
    lines += ["", "## Summary at 100% drift, mean over the six corpora (benchmark metric; tokens relative to the clairvoyant build)", "",
              "| Axis | static | adaptive | adaptive - static | static tokens | lean + controller | robust + controller |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for axis in AXES:
        rows = [(res, c) for c, res in allres.items() if all((s, f"{axis}/100") in res for s in SEEDS)]
        if not rows:
            continue
        st = mean([cell_acc(r, axis, "100", "static", "benchmark") for r, _c in rows])
        ad = mean([cell_acc(r, axis, "100", "quwarts", "benchmark") for r, _c in rows])
        rel = lambda pol: mean([cell_tokens(r, axis, "100", pol) / cell_tokens(r, axis, "100", "clairvoyant") for r, _c in rows])  # noqa: E731
        lines.append(f"| {axis} | {st:.3f} | {ad:.3f} | {ad - st:+.3f} | {rel('static'):.2f} | {rel('quwarts'):.2f} | {rel('robust'):.2f} |")
    lines += ["", "## Replay audit: small prompts against the robust prompt on a document sample", "",
              "| Corpus | Documents | W0 fields (lean prompt): agreement | accuracy, lean - robust prompt [95% CI] | other fields (patch prompt): agreement | accuracy, patch - robust prompt [95% CI] |",
              "|---|---|---:|---|---:|---|"]
    for c in CORPORA:
        path = context(c).folder / "audit.json"
        if not path.exists():
            continue
        a = json.loads(path.read_text())
        cells = []
        for kind in ("lean", "patch"):
            k = a[kind]
            ci = k.get("small_minus_robust_ci")
            cells.append(f"{k['agreement']:.3f}")
            cells.append(f"{k['small_minus_robust']:+.3f} [{ci[0]:+.3f}, {ci[1]:+.3f}] ({k['cells_gold']} cells)" if ci else "no gold map")
        docs = ", ".join(f"{t} {n}" for t, n in a["documents"].items())
        lines.append(f"| {c} | {docs} | " + " | ".join(cells) + " |")
    text = "\n".join(lines)
    (DROOT / "RESULTS.md").write_text(text + "\n")
    return text



# ------------------------------------------------------------------------------------------ audit

AUDIT_DOCS = {"finan": 5, "med": 10, "player": 10}  # documents per table (default 20); these corpora have long documents


def audit_setup(corpus: str):
    """The replay's approximation, measured on a document sample: the lean build's prompt (W0's fields)
    and a patch's prompt (the other fields) against the robust read's prompt (all fields)."""

    from dataclasses import replace

    ctx = context(corpus)
    rng = random.Random(f"drift-audit:{corpus}")
    sample = {}
    for r in ctx.reads:
        names = ctx.names[r.table]
        sample[r.table] = sorted(rng.sample(names, min(len(names), AUDIT_DOCS.get(corpus, 20))))
    lean = {r.table: set(r.attributes) for r in ctx.lean_reads}
    reads = {"lean": [C.Read(r.table, "audit:lean", tuple(sorted(lean[r.table]))) for r in ctx.reads if lean.get(r.table)],
             "patch": [C.Read(r.table, "audit:patch", tuple(a for a in r.attributes if a not in lean.get(r.table, set())))
                       for r in ctx.reads]}
    reads["patch"] = [r for r in reads["patch"] if r.attributes]
    root = ctx.scratch / "audit_docs"
    tables = []
    for tb in ctx.spec.tables:
        d = root / tb.sql_name
        d.mkdir(parents=True, exist_ok=True)
        for name in sample.get(tb.sql_name, []):
            link = d / name
            if not link.exists():
                link.symlink_to(Path(ctx.docs[tb.sql_name][name]).resolve())
        tables.append(replace(tb, doc_dir=d))
    view = replace(ctx.spec, tables=tuple(tables))
    return ctx, sample, reads, view


def audit_read(corpus: str, deadline: float, workers: int) -> dict[str, Any]:
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.llm.openrouter import load_env_file, make_caller
    from quwarts.core.router.executor import run_reads
    from quwarts.core.router.registry import PROJECT

    ctx, sample, reads, view = audit_setup(corpus)
    load_env_file(PROJECT / ".env")
    caller = make_caller(TokenLedger(theta=10**12), max_tokens=700)
    stats = run_reads(view, reads["lean"] + reads["patch"], {}, ctx.fields, caller, ROOT / corpus / "audit_reads.jsonl", workers,
                      long_documents="chain", deadline=deadline)
    stats["spent_this_run"] = caller.ledger.spent
    return stats


def audit(corpus: str) -> dict[str, Any]:
    """Per column: agreement of the lean or patch prompt's value with the robust read's value, and each
    one's accuracy against gold where the corpus maps documents to gold rows (AUDIT: reads gold)."""

    from quwarts.eval.represent_eval import gold_cells
    from quwarts.eval.tolerant_score import cell

    ctx, sample, reads, _view = audit_setup(corpus)
    docs = {t: {d: ctx.docs[t][d] for d in ds} for t, ds in sample.items()}
    robust = C.read_values(docs, ctx.reads, ctx.fields, journal_rows(corpus))
    rows = {}
    path = ROOT / corpus / "audit_reads.jsonl"
    for line in path.read_text().splitlines() if path.exists() else []:
        if line.strip():
            row = json.loads(line)
            rows[row["prompt_sha"]] = row
    small = C.read_values(docs, reads["lean"], ctx.fields, rows)
    small_patch = C.read_values(docs, reads["patch"], ctx.fields, rows)
    gold = gold_cells(corpus, ctx.spec)
    out: dict[str, Any] = {"documents": {t: len(d) for t, d in sample.items()}, "columns": {}}
    paired_cells: dict[str, list[float]] = {"lean": [], "patch": []}
    for kind, got, rds in (("lean", small, reads["lean"]), ("patch", small_patch, reads["patch"])):
        for r in rds:
            for a in r.attributes:
                n = agree = both = 0
                acc_small = acc_robust = n_gold = 0
                for d in sample[r.table]:
                    x, y = got.get((r.table, d), {}).get(a), robust.get((r.table, d), {}).get(a)
                    if (r.table, d) not in got or (r.table, d) not in robust:
                        continue
                    n += 1
                    agree += cell(x) == cell(y)
                    g = gold.get((r.table, d), {}).get(a.lower())
                    if g is not None and cell(g) is not None:
                        n_gold += 1
                        acc_small += cell(x) == cell(g)
                        acc_robust += cell(y) == cell(g)
                        paired_cells[kind].append(float(cell(x) == cell(g)) - float(cell(y) == cell(g)))
                out["columns"][f"{r.table}.{a}"] = {"prompt": kind, "n": n, "agreement": round(agree / n, 3) if n else None,
                                                    "n_gold": n_gold,
                                                    "accuracy_small_prompt": round(acc_small / n_gold, 3) if n_gold else None,
                                                    "accuracy_robust_prompt": round(acc_robust / n_gold, 3) if n_gold else None}
    cols = out["columns"].values()
    for kind in ("lean", "patch"):
        cs = [c for c in cols if c["prompt"] == kind and c["n"]]
        g = [c for c in cs if c["n_gold"]]
        out[kind] = {"columns": len(cs), "agreement": round(mean([c["agreement"] for c in cs]), 3) if cs else None,
                     "accuracy_small_prompt": round(mean([c["accuracy_small_prompt"] for c in g]), 3) if g else None,
                     "accuracy_robust_prompt": round(mean([c["accuracy_robust_prompt"] for c in g]), 3) if g else None,
                     "gold_columns": len(g)}
        if len(paired_cells[kind]) > 2:
            from quwarts.eval.represent_eval import paired_ci

            out[kind]["cells_gold"] = len(paired_cells[kind])
            out[kind]["small_minus_robust"] = round(mean(paired_cells[kind]), 3)
            out[kind]["small_minus_robust_ci"] = [round(x, 3) for x in paired_ci(paired_cells[kind])]
    (ctx.folder / "audit.json").write_text(json.dumps(out, indent=1))
    return out



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", choices=CORPORA)
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--read", action="store_true")
    parser.add_argument("--raw", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--audit-read", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--deadline", type=float, default=None)
    parser.add_argument("--workers", type=int, default=48)
    args = parser.parse_args(argv)
    if args.estimate:
        print(json.dumps(estimate(args.corpus)))
    if args.read:
        print(json.dumps(read(args.corpus, args.deadline or 120, args.workers)))
    if args.raw:
        out = raw(args.corpus)
        print(json.dumps({k: (v if k != "documents_missing" else v[:10]) for k, v in out.items()})[:3000])
    if args.replay:
        print(json.dumps(replay(args.corpus, args.deadline)))
    if args.audit_read:
        print(json.dumps(audit_read(args.corpus, args.deadline or 120, args.workers)))
    if args.audit:
        out = audit(args.corpus)
        print(json.dumps({k: v for k, v in out.items() if k != "columns"}))
    if args.report:
        print(report())
    return 0


if __name__ == "__main__":
    sys.exit(main())

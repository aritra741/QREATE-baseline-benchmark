"""Triggered materialization: answer, patch (targeted extraction), or rebuild, per incoming query.

The master database holds the columns of a *design*: the attributes its build workload needs, extracted
by one shared read per document with field descriptions informed by how that workload uses them. For
each incoming query the controller does one of three things.

* **Answer.** Every column the query needs is materialized for every document that can affect its
  answer: zero reads.
* **Patch** (targeted extraction). Read only the missing columns, and only for documents that can
  affect the answer: a top-level conjunct of the WHERE clause over columns that are fully materialized
  is evaluated on the master database, and documents it excludes cannot change the answer (their rows
  are filtered out whatever the new column holds). The reads use the build's reader (single read, or a
  chained read for long documents), so patched cells have the build's fidelity; they are kept, and a
  later query reuses them.
* **Rebuild.** One shared read of the corpus with the design of the build workload plus every query seen
  since the last build.

When to rebuild. OnlinePT (Bruno & Chaudhuri, ICDE 2007) keeps, for each alternative physical design,
the benefit it would have had on the queries seen since the last change and switches when that benefit
exceeds the transition cost (a ski-rental argument, constant competitive ratio). Here the alternative is
the rebuilt design, its benefit on a query is the extraction it would have saved (the patch tokens), and
the transition cost is the rebuild's tokens. Two additions:

* a patch that alone would cost at least a rebuild is replaced by the rebuild (which covers more);
* a rebuild is considered only if the remaining rent can reach its cost: with robust reads, all future
  patches together cost at most patching every cell of the robust design still missing, and when that is
  below the rebuild's cost no query sequence makes the rebuild pay (in extraction cost, patching then
  dominates rebuilding: each document is read at most once more, a rebuild reads every document);
* the drift test is the prediction of ski rental with predictions (Purohit, Svitkina & Kumar, NeurIPS
  2018). Their deterministic rule needs only a binary prediction, "will the total rent exceed the buy
  cost?", and buys once the rent reaches lambda * R when the prediction says yes and R / lambda when it
  says no; it is (1 + lambda)-competitive when the prediction is right and (1 + 1/lambda)-competitive
  whatever the prediction. The prediction here is whether the recent workload has drifted significantly
  from the build workload (``drift.drift_test``: CliffGuard's distance, resampling-calibrated): a
  sustained shift in how the workload uses columns predicts more misses; scattered novel queries do not.
  After a rebuild the build workload absorbs the queries since the last build.

Policies: ``patch`` (never rebuild), ``eager`` (rebuild at every miss), ``onlinept`` (benefit rule, lambda = 1,
no prediction), ``drift`` (ski rental with the drift prediction; the proposed policy).

What a read extracts. A read costs about the document's length whatever the number of fields, so by
default (``robust``) every read extracts every attribute of the table's schema that the document does not
have yet: a patch of a document fills all its missing columns, and a rebuild uses the robust design
(CliffGuard's robust designs: good for a neighbourhood of the observed workload). With ``robust=False``
patches extract only the query's missing columns and rebuilds cover only the observed workload (an
ablation).
"""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from quwarts.core.adapt import drift as D
from quwarts.core.router import chunked
from quwarts.core.router.context_probe import V3, protocol_field_specs, render_prompt
from quwarts.core.router.executor import Read
from quwarts.core.router.needs import query_needs
from quwarts.core.router.workload_features import table_attribute_names, usage_phrase, workload_features

SHARED = "__workload__"
POLICIES = ("patch", "eager", "onlinept", "drift")


def design(spec, queries: dict[str, str], robust: bool = False):
    """Field specs and shared reads for a workload (the build's rule: needs, benchmark descriptions,
    usage phrases from how the workload uses each attribute).

    ``robust``: also every other attribute of the tables the workload reads (the benchmark schema), in
    the spirit of CliffGuard's robust designs (good for a neighbourhood of the observed workload, not only
    for it). A shared read's cost grows only with the field list's length, so covering the neighbourhood
    is cheap, and a later query on another column of those tables needs no patch."""

    from quwarts.core.router.needs import Need

    table_attrs = table_attribute_names(spec, queries)
    needs = [n for q, s in queries.items() for n in query_needs(q, s, table_attrs)]
    if robust:
        schema = spec.benchmark_attribute_descriptions(purpose="protocol")
        have = {(n.table, n.attribute) for n in needs}
        for table in sorted({n.table for n in needs}):
            for attr in sorted(schema.get(spec.table(table).attributes_key, {})):
                if (table, attr) not in have:
                    needs.append(Need("__schema__", table, attr, "value"))
    wf = workload_features(spec, queries)
    fields = protocol_field_specs(spec, needs)
    fields = {q: replace(f, usage=usage_phrase(wf["attributes"][q])) if q in wf["attributes"] else f
              for q, f in fields.items()}
    reads = [Read(t, SHARED, tuple(sorted({n.attribute for n in needs if n.table == t})))
             for t in sorted({n.table for n in needs})]
    return fields, reads


def query_attributes(spec, qid: str, sql: str, context: dict[str, str]) -> dict[str, set[str]]:
    table_attrs = table_attribute_names(spec, {**context, qid: sql})
    out: dict[str, set[str]] = {}
    for n in query_needs(qid, sql, table_attrs):
        out.setdefault(n.table, set()).add(n.attribute)
    return out


class Costs:
    """Token estimates of reads (prompt + answer) from each document's length: a document that fits the
    window is one read, a longer one is ceil(tokens / chunk size) chunk reads with a carried note."""

    ANSWER_PER_FIELD = 12
    NOTE = 120

    def __init__(self, doc_tokens: dict[tuple[str, str], int]):
        self.doc_tokens = doc_tokens
        self.window = int(V3["window_tokens"])
        self._wrapper: dict[tuple, int] = {}

    def wrapper(self, specs) -> int:
        from quwarts.core.retrieve_extract.tokens import count_tokens

        key = tuple(f.line() for f in specs)
        if key not in self._wrapper:
            self._wrapper[key] = count_tokens(render_prompt("", list(specs), None)) + 20
        return self._wrapper[key]

    def read(self, table: str, doc: str, specs) -> int:
        tokens = self.doc_tokens[(table, doc)]
        per_call = self.wrapper(specs) + 8 + self.ANSWER_PER_FIELD * len(specs)
        if tokens <= self.window:
            return tokens + per_call
        n = math.ceil(tokens / chunked.chunk_tokens(self.window))
        return tokens + n * (per_call + 2 * self.NOTE)

    def reads(self, table: str, docs, specs) -> int:
        return sum(self.read(table, d, specs) for d in docs) if specs else 0


@dataclass
class Step:
    pos: int
    qid: str
    action: str
    missing: dict[str, list[str]] = field(default_factory=dict)
    scope_docs: int = 0
    patch_tokens: int = 0
    rebuild_tokens: int = 0
    benefit: int = 0
    drift: dict[str, Any] = field(default_factory=dict)
    new_template: bool = False
    version: int = 0
    spent: int = 0


class Materializer:
    """The decision loop. ``executor`` performs reads and database changes (or only accounts for them)."""

    def __init__(self, spec, build_queries: dict[str, str], docs: dict[str, list[str]], costs: Costs, executor,
                 policy: str, alpha: float = 0.05, window: int = 20, min_window: int = 8, trust: float = 0.5,
                 robust: bool = True):
        assert policy in POLICIES
        self.spec, self.docs, self.costs, self.executor, self.policy = spec, docs, costs, executor, policy
        self.alpha, self.window, self.min_window, self.trust, self.robust = alpha, window, min_window, trust, robust
        self.build_queries = dict(build_queries)
        self.recent: list[tuple[str, str]] = []
        self.benefit = 0
        self.version = 0
        self.fields, self.reads = design(spec, self.build_queries)
        self.materialized: dict[tuple[str, str], set[str]] = {
            (r.table, a): set(docs[r.table]) for r in self.reads for a in r.attributes}
        self.templates = {D.template(s) for s in self.build_queries.values()}
        self.steps: list[Step] = []

    # -- state ---------------------------------------------------------------------------------------
    def to_state(self) -> dict[str, Any]:
        return {"policy": self.policy, "build_queries": self.build_queries, "recent": self.recent,
                "benefit": self.benefit, "version": self.version, "templates": sorted(self.templates),
                "materialized": [[t, a, sorted(d)] for (t, a), d in self.materialized.items()],
                "steps": [s.__dict__ for s in self.steps]}

    def load_state(self, state: dict[str, Any]) -> None:
        self.build_queries = state["build_queries"]
        self.recent = [tuple(x) for x in state["recent"]]
        self.benefit, self.version = state["benefit"], state["version"]
        self.templates = set(state["templates"])
        self.materialized = {(t, a): set(d) for t, a, d in state["materialized"]}
        self.steps = [Step(**s) for s in state["steps"]]
        self.fields, self.reads = design(self.spec, self.build_queries)

    # -- one query -----------------------------------------------------------------------------------
    def context(self) -> dict[str, str]:
        return {**self.build_queries, **dict(self.recent)}

    def fully(self, table: str, attr: str) -> bool:
        return self.materialized.get((table, attr), set()) >= set(self.docs[table])

    def step(self, qid: str, sql: str) -> Step:
        pos = len(self.steps)
        seen = {**self.context(), qid: sql}
        need = query_attributes(self.spec, qid, sql, seen)
        new_template = D.template(sql) not in self.templates
        missing: dict[str, set[str]] = {}
        scope: dict[str, list[str]] = {}
        for table, attrs in need.items():
            if table not in self.docs:
                continue
            lacking = {a for a in attrs if not self.fully(table, a)}
            if not lacking:
                continue
            known = {a for a in self.all_attributes(table) if self.fully(table, a)}
            rows = self.executor.pushdown(table, sql, known, len(need) == 1)
            rows = list(self.docs[table]) if rows is None else [d for d in self.docs[table] if d in rows]
            todo = [d for d in rows if any(d not in self.materialized.get((table, a), set()) for a in lacking)]
            if todo:
                missing[table], scope[table] = lacking, todo
        self.recent.append((qid, sql))
        self.templates.add(D.template(sql))
        st = Step(pos, qid, "answer", {t: sorted(a) for t, a in missing.items()},
                  sum(len(v) for v in scope.values()), new_template=new_template, benefit=self.benefit, version=self.version)
        if not missing:
            self.steps.append(st)
            return st
        cand_fields, cand_reads = design(self.spec, self.context(), robust=self.robust)
        extract = {t: set(missing[t]) for t in missing}
        if self.robust:  # read once, fill every column of the schema the documents lack
            for r in cand_reads:
                if r.table in extract:
                    extract[r.table] |= {a for a in r.attributes if not self.fully(r.table, a)}
        specs = {t: [cand_fields[f"{t}.{a}"] for a in sorted(extract[t]) if f"{t}.{a}" in cand_fields] for t in missing}
        st.patch_tokens = sum(self.costs.reads(t, scope[t], specs[t]) for t in missing)
        st.rebuild_tokens = sum(self.costs.reads(r.table, self.docs[r.table], [cand_fields[f"{r.table}.{a}"] for a in r.attributes])
                                for r in cand_reads if r.table in self.docs)
        window = [s for _q, s in self.recent[-self.window:]]
        st.drift = D.drift_test(list(self.build_queries.values()), window) if len(window) >= self.min_window else \
            {"p": 1.0, "n_window": len(window)}
        drifted = st.drift.get("p", 1.0) < self.alpha
        # Remaining-rent cap. With robust reads every future patch fills cells of the robust design that
        # are still missing, so the whole future rent is at most the cost of patching all of them now. If
        # that is below the rebuild cost, no query sequence can make the rebuild pay for itself.
        if self.robust:
            cap = 0
            for r in cand_reads:
                if r.table not in self.docs:
                    continue
                gaps = [a for a in r.attributes if not self.fully(r.table, a)]
                lacking_docs = [d for d in self.docs[r.table] if any(d not in self.materialized.get((r.table, a), set()) for a in gaps)]
                cap += self.costs.reads(r.table, lacking_docs, [cand_fields[f"{r.table}.{a}"] for a in gaps])
            st.drift = {**st.drift, "rent_cap": cap}
        else:
            cap = None
        rebuild = {
            "patch": False,
            "eager": True,
            "onlinept": st.patch_tokens >= st.rebuild_tokens or self.benefit + st.patch_tokens >= st.rebuild_tokens,
            "drift": (cap is None or cap >= st.rebuild_tokens) and (st.patch_tokens >= st.rebuild_tokens or
                     self.benefit + st.patch_tokens >= (self.trust if drifted else 1 / self.trust) * st.rebuild_tokens),
        }[self.policy]
        if rebuild:
            st.spent = self.executor.rebuild(cand_fields, cand_reads, seen)
            self.build_queries = seen
            self.recent = []
            self.benefit = 0
            self.fields, self.reads = cand_fields, cand_reads
            self.materialized = {(r.table, a): set(self.docs[r.table]) for r in cand_reads for a in r.attributes}
            st.action = "rebuild"
        else:
            spent = 0
            for t in missing:
                spent += self.executor.patch(t, scope[t], specs[t], cand_fields, seen)
                for f in specs[t]:
                    self.materialized.setdefault((t, f.name), set()).update(scope[t])
            st.spent = spent
            self.benefit += st.patch_tokens
            st.action = "patch"
        self.version += 1
        st.version = self.version
        st.benefit = self.benefit
        self.steps.append(st)
        return st

    def all_attributes(self, table: str) -> set[str]:
        return {a for (t, a) in self.materialized if t == table}


# ------------------------------------------------------------------------------------------ pushdown

def pushdown_conjuncts(sql: str, table: str, known: set[str]) -> str | None:
    """The top-level AND conjuncts of a single-table query's WHERE clause that use only ``known`` columns
    and no subquery, as a SQL condition (None when there is none)."""

    import sqlglot
    from sqlglot import exp

    tree = sqlglot.parse_one(sql, read="sqlite")
    tables = {t.name for t in tree.find_all(exp.Table)}
    if tables != {table} or tree.find(exp.Subquery) is not None or len(list(tree.find_all(exp.Select))) != 1:
        return None
    where = tree.args.get("where")
    if where is None:
        return None
    parts, stack = [], [where.this]
    while stack:
        node = stack.pop()
        if isinstance(node, exp.And):
            stack += [node.left, node.right]
        elif isinstance(node, exp.Paren) and isinstance(node.this, exp.And):
            stack.append(node.this)
        else:
            parts.append(node)
    keep = [p for p in parts if {c.name for c in p.find_all(exp.Column)} and
            {c.name for c in p.find_all(exp.Column)} <= known]
    if not keep:
        return None
    return " AND ".join(f"({p.sql(dialect='sqlite')})" for p in keep)


def evaluate_scope(db: Path, table: str, condition: str) -> set[str] | None:
    """Documents whose row satisfies ``condition`` in ``db``. Valid as a scope only while the query path
    evaluates these predicates as plain SQL (no realized signature column), which is checked here."""

    conn = sqlite3.connect(db)
    try:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
        realized = [c for c in cols if c.startswith("sig_") and c.endswith("_r")]
        for c in realized:
            if conn.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{c}" = 1').fetchone()[0]:
                return None
        rows = conn.execute(f'SELECT doc_id FROM "{table}" WHERE {condition}').fetchall()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return {_doc_name(r[0]) for r in rows}


def _doc_name(doc_id: Any) -> str:
    s = str(doc_id)
    return s if s.endswith(".txt") else f"{Path(s).name}.txt"


# ------------------------------------------------------------------------------------------ read values

def read_values(docs: dict[str, dict[str, Path]], reads, fields, by_sha: dict[str, dict]) -> dict:
    """``{(table, doc): {attr: raw value}}`` for the given documents under a design, looked up by prompt
    hash in the read journal (single reads; chained reads are replayed with their carried notes and
    combined with ``chunked.reduce_chunks``). Documents whose reads are missing are left out."""

    from quwarts.core.retrieve_extract.tokens import count_tokens
    from quwarts.core.router.context_probe import truncate
    from quwarts.core.router.corpus_features import read_document
    from quwarts.core.router.probes import parse_fields
    import hashlib

    def sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    window = int(V3["window_tokens"])
    out = {}
    for read in reads:
        specs = [fields[f"{read.table}.{a}"] for a in read.attributes]
        names = list(read.attributes)
        for doc, path in docs.get(read.table, {}).items():
            text = read_document(path)
            if count_tokens(text) <= window:
                row = by_sha.get(sha(render_prompt(truncate(text, window), specs, None)))
                if row is not None:
                    parsed = parse_fields(row["response"], names)
                    out[(read.table, doc)] = {a: parsed.get(a) for a in names}
                continue
            carry, answers = "", []
            pieces = chunked.split_chunks(text, chunked.chunk_tokens(window))
            for i, piece in enumerate(pieces):
                row = by_sha.get(sha(chunked.render_chunk_prompt(piece, specs, carry, i + 1, len(pieces)))) or \
                    by_sha.get(sha(chunked.render_chunk_prompt(chunked.compact(piece), specs, carry, i + 1, len(pieces))))
                if row is None:
                    break
                parsed = parse_fields(row["response"], names)
                answers.append({a: parsed.get(a) for a in names})
                carry = chunked.parse_carry(row["response"], carry)
            if len(answers) == len(pieces):
                out[(read.table, doc)] = {a: chunked.reduce_chunks(answers, fields[f"{read.table}.{a}"])[0] for a in names}
    return out

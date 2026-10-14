"""A view agent: one lossless extraction, a view per query whose columns take the form that query's SQL implies.

The store keeps every value as it was read (lists, stated text, the document's spelling). For each query and each column
the query reads, an agent (Claude) sees only the query's SQL, the column's description, how the query uses the column (its
constants, groupings, numeric comparisons, join partner and the partner's values) and the column's distinct stored values
with row counts. It never sees the question text or the answer key. It chooses:
  keep  the stored values already fit the query
  sql   a deterministic SQLite expression over the column, applied to every row (first item of a list, year of a date,
        a number from text); written once by the agent
  map   a judgment or knowledge mapping of each distinct stored value (a category, a region, the partner table's
        spelling); the agent states the rule, then maps the distinct values in batches
The view is the store with those columns rewritten, completed and scored against the answer keys. Cost: the agent's
tokens, which grow with distinct values, not with documents.

    ANTHROPIC_API_KEY=... PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_view_agent --store claude-haiku-5-5 --corpus art
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sqlglot
from sqlglot import exp

from quwarts.eval import drift_live as D
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_tau import EXP, TAUS, score_multi
from quwarts.eval.validate_conflicts import load

REPO = EXP.parents[1]
MODEL = "claude-haiku-5-5"
_lock = threading.Lock()


class Agent:
    def __init__(self, model: str, log: Path):
        import anthropic

        self.anthropic = anthropic
        self.client = anthropic.Anthropic(max_retries=2)
        self.model, self.log = model, log
        self.tokens = {"input": 0, "output": 0, "calls": 0}

    def ask(self, prompt: str, max_tokens: int = 4000) -> dict:
        wait = 10.0
        while True:
            try:
                r = self.client.messages.create(model=self.model, max_tokens=max_tokens,
                                                system="You prepare database views. Reply with one JSON object only.",
                                                messages=[{"role": "user", "content": prompt}])
                break
            except (self.anthropic.RateLimitError, self.anthropic.InternalServerError, self.anthropic.APIConnectionError):
                time.sleep(wait)
                wait = min(wait * 1.5, 120.0)
        text = "".join(b.text for b in r.content if b.type == "text")
        with _lock:
            self.tokens["input"] += r.usage.input_tokens
            self.tokens["output"] += r.usage.output_tokens
            self.tokens["calls"] += 1
            with self.log.open("a") as h:
                h.write(json.dumps({"prompt": prompt[:4000], "response": text}) + "\n")
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return {}
        try:
            return json.JSONDecoder().raw_decode(text[m.start():])[0]
        except json.JSONDecodeError:
            return {}


def columns_and_uses(sql: str) -> dict[str, dict]:
    """table.column -> how the query uses it (constants, grouped, numeric comparison, join partner)."""
    tree = sqlglot.parse_one(sql, read="sqlite")
    alias = {t.alias_or_name: t.name for t in tree.find_all(exp.Table)}
    single = next(iter(alias.values())) if len(set(alias.values())) == 1 else None
    names = {a.alias.lower() for a in tree.find_all(exp.Alias)}

    def key(c):
        t = alias.get(c.table, c.table) if c.table else single
        return f"{t}.{c.name}" if t and not (not c.table and c.name.lower() in names) else None

    out: dict[str, dict] = {}
    for c in tree.find_all(exp.Column):
        k = key(c)
        if k:
            out.setdefault(k, {"constants": set(), "grouped": False, "numeric": False, "join_partner": None})
    for node in tree.find_all(exp.EQ, exp.Like, exp.In, exp.NEQ):
        col = node.find(exp.Column)
        if col is not None and key(col) in out:
            out[key(col)]["constants"] |= {lit.this for lit in node.find_all(exp.Literal) if lit.is_string}
    for node in tree.find_all(exp.Between, exp.GT, exp.GTE, exp.LT, exp.LTE):
        for col in node.find_all(exp.Column):
            if key(col) in out and any(not lit.is_string for lit in node.find_all(exp.Literal)):
                out[key(col)]["numeric"] = True
    g = tree.find(exp.Group)
    if g is not None:
        for col in g.find_all(exp.Column):
            if key(col) in out:
                out[key(col)]["grouped"] = True
    for j in tree.find_all(exp.Join):
        on = j.args.get("on")
        if on is None:
            continue
        for eq in on.find_all(exp.EQ):
            if isinstance(eq.this, exp.Column) and isinstance(eq.expression, exp.Column):
                a, b = key(eq.this), key(eq.expression)
                if a in out and b in out:
                    out[a]["join_partner"], out[b]["join_partner"] = b, a
    return out


def distinct(con, t: str, a: str, limit: int | None = None) -> list[tuple]:
    q = f'SELECT "{a}", COUNT(*) FROM "{t}" WHERE "{a}" IS NOT NULL AND TRIM(CAST("{a}" AS TEXT)) <> \'\' GROUP BY 1 ORDER BY 2 DESC'
    rows = con.execute(q + (f" LIMIT {limit}" if limit else "")).fetchall()
    return rows


DECIDE = """A table was extracted from documents; each value is stored as the document states it (a list is stored as
"A || B"). The SQL query below will run on a view of this table EXACTLY as written. Decide how one column must be stored
in that view so that the query returns what its author means. Judge only from the SQL and the data.

Query:
{sql}

Column: {col}  ({desc})
How the query uses it: {uses}
Stored values ({n} distinct; most frequent first, with row counts):
{values}
{partner}
Choose one operation:
- "keep": the stored values already fit the query as written.
- "sql": a deterministic SQLite expression that computes the needed value from the stored one for every row; refer to the
  stored value as {name} (examples: the first item of a list, the year of a date as an INTEGER, a number in a text).
- "map": a judgment or knowledge mapping from each distinct stored value to the value the query expects (for example a
  category the query names, a region, the partner table's spelling of the same entity); state the rule precisely.
Reply with JSON: {{"operation": "keep|sql|map", "sql_expression": "...", "mapping_rule": "...", "reason": "..."}}"""

MAP = """Map stored values of the column {col} to the form a SQL query expects.
Query:
{sql}
Rule: {rule}
{targets}For each stored value below give the value to store in the view. Use null to leave a value unchanged.
Reply with JSON: {{"mapping": {{"<stored value>": "<value to store or null>", ...}}}}
Stored values:
{values}"""


def plan_column(agent: Agent, con, sql: str, col: str, use: dict, desc: str) -> dict:
    t, a = col.split(".", 1)
    vals = distinct(con, t, a)
    if not vals:
        return {"operation": "keep", "reason": "no values"}
    uses = []
    if use["constants"]:
        uses.append("compared with the constants " + ", ".join(repr(x) for x in sorted(use["constants"])))
    if use["numeric"]:
        uses.append("compared numerically")
    if use["grouped"]:
        uses.append("grouped by")
    if use["join_partner"]:
        uses.append(f"joined with {use['join_partner']}")
    partner = ""
    if use["join_partner"]:
        pt, pa = use["join_partner"].split(".", 1)
        pv = distinct(con, pt, pa, 150)
        partner = f"\nValues of the join partner {use['join_partner']} (most frequent first):\n" + "\n".join(f"  {v!r} ({n})" for v, n in pv) + "\n"
    shown = vals[:150]
    d = agent.ask(DECIDE.format(sql=sql, col=col, desc=desc or "no description", uses="; ".join(uses) or "selected or aggregated",
                                n=len(vals), values="\n".join(f"  {v!r} ({n})" for v, n in shown), partner=partner, name=a))
    d["values"] = len(vals)
    if d.get("operation") == "map":
        targets = ""
        if use["constants"]:
            targets = "Values the query names: " + ", ".join(repr(x) for x in sorted(use["constants"])) + "\n"
        if use["join_partner"]:
            targets += "The partner column's values: " + ", ".join(repr(v) for v, _ in distinct(con, *use["join_partner"].split(".", 1), 300)) + "\n"
        mapping = {}
        allv = [v for v, _ in vals]
        for i in range(0, len(allv), 120):
            batch = allv[i:i + 120]
            m = agent.ask(MAP.format(col=col, sql=sql, rule=d.get("mapping_rule", ""), targets=targets,
                                     values="\n".join(f"  {v!r}" for v in batch)), max_tokens=8000).get("mapping", {})
            for v in batch:
                if str(v) in m and m[str(v)] is not None:
                    mapping[str(v)] = m[str(v)]
        d["mapping"] = mapping
    return d


def apply(view: Path, col: str, d: dict) -> str | None:
    t, a = col.split(".", 1)
    con = sqlite3.connect(view)
    try:
        if d.get("operation") == "sql" and d.get("sql_expression"):
            con.execute(f'UPDATE "{t}" SET "{a}" = ({d["sql_expression"]}) WHERE "{a}" IS NOT NULL')
        elif d.get("operation") == "map" and d.get("mapping"):
            for v, new in d["mapping"].items():
                con.execute(f'UPDATE "{t}" SET "{a}" = ? WHERE CAST("{a}" AS TEXT) = ?', (new, v))
        con.commit()
        return None
    except sqlite3.Error as exc:
        return str(exc)
    finally:
        con.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True, help="conflict_ours/<store>/<corpus>/asread/master.db (claude-haiku-5-5 or gold)")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    c = a.corpus
    ctx = D.R.context(c)
    queries = load(c)
    for q, s in queries.items():
        ctx.catalog[q] = s
    master = REPO / "results" / "conflict_ours" / a.store / c / "asread" / "master.db"
    out = REPO / "results" / "conflict_agent" / f"{a.store}-{a.model}" / c
    (out / "views").mkdir(parents=True, exist_ok=True)
    agent = Agent(a.model, out / "agent_calls.jsonl")
    fields = fields_of(c)
    con = sqlite3.connect(master)
    have = {(t, r[1].lower()) for t in [x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            for r in con.execute(f'PRAGMA table_info("{t}")')}

    def one(q):
        sql = queries[q]
        uses = {k: v for k, v in columns_and_uses(sql).items() if (k.split(".")[0], k.split(".")[1].lower()) in have}
        local = sqlite3.connect(master)
        plans = {col: plan_column(agent, local, sql, col, use, getattr(fields.get(col), "description", "")) for col, use in uses.items()}
        local.close()
        view = out / "views" / f"{q.replace(':', '_').replace('#', '_')}.db"
        shutil.copy2(master, view)
        errors = {col: e for col, d in plans.items() if (e := apply(view, col, d))}
        D.R.complete(c, view)
        return q, view, plans, errors

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(one, list(queries)))
    sc = score_multi(c, [(q, v) for q, v, _, _ in res])
    report = {"store": a.store, "model": a.model, "agent_tokens": agent.tokens,
              "per_query": {q: {"score": {f"{t:.0%}": sc[q].get(t) for t in TAUS},
                                "plans": {col: {k: v for k, v in d.items() if k != "mapping"} | {"mapped_values": len(d.get("mapping") or {})} for col, d in plans.items()},
                                "errors": errors} for q, _, plans, errors in res}}
    (out / "per_query.json").write_text(json.dumps(report, indent=1, default=str))
    mean = sum(v["score"]["20%"] for v in report["per_query"].values()) / len(report["per_query"])
    print(f"{c} store={a.store} mean@20 {mean:.3f}  agent {agent.tokens['calls']} calls, "
          f"{(agent.tokens['input'] + agent.tokens['output']) / 1e6:.3f}M tokens", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

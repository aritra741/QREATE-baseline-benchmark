"""Representation layer: one extraction, stored raw; views written the way the workload reads them.

The shared read extracts each value once. What the workload needs on top is a *representation*: the
spelling its equality literals, ``IN`` lists, joins and groups can see (``grammar``). The layer keeps the
raw extraction untouched and derives a view in four tiers, cheapest first:

* **T0 rules** (``normalize``): cleaning, vocabulary spelling, workload conventions, containment, one
  value or a set. Free.
* **T1 programs** (``programs``): FlashFill-style string programs per pattern class, learned from T0's
  own confident rewrites. Free.
* **T2 model** (``llm``): residual distinct values rewritten by the model, batched and memoized; its
  cost scales with distinct values, not rows or documents. Budgeted by ``router``; in ``cascade`` mode
  the model labels two representatives per uncovered pattern class and programs generalize.
* **Entity resolution** (``resolve``): join columns share one domain (entity side spelling), raw
  grouping columns merge folded duplicates.

The view is a materialized copy of the raw database with rewritten cells, a ``__rep_map`` table (raw cell,
view cell, tier) and a manifest. Rebuilding a view from the raw database and the maps costs no model call.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from quwarts.core.represent import programs as T1
from quwarts.core.represent.grammar import grammar, join_pairs
from quwarts.core.represent.llm import Journal, estimate_tokens, normalize as t2_normalize
from quwarts.core.represent.normalize import Target, combine, parts, status, t0_part, targets
from quwarts.core.represent.resolve import entity_side, group_merges, match_join, rewrite
from quwarts.core.represent.router import ColumnPlan, choose


@dataclass
class Config:
    t0: bool = True
    t1: bool = True
    t2: str = "none"  # none | all | cascade
    budget: int | None = None  # model-tier tokens (None: unlimited when t2 != none)
    er: bool = True
    er_model: bool = False
    group: bool = True
    demos: bool = True  # the model sees the column's own rewrites as demonstrations
    cardinality: bool = True  # equality-only use of a declared multi-valued column reads it as single-valued

    @property
    def name(self) -> str:
        if not self.t0:
            return "raw"
        n = "t0" + ("+t1" if self.t1 else "") + ("+er" if self.er else "") + ("+group" if self.group else "")
        if self.t2 != "none":
            n += f"+t2_{self.t2}" + (f"@{self.budget}" if self.budget is not None else "")
        if self.er_model:
            n += "+er_model"
        if self.t2 != "none" and not self.demos:
            n += "+nodemo"
        if not self.cardinality:
            n += "+declared_cardinality"
        return n


def demos(s: dict[str, Any]) -> list[tuple[str, str]]:
    """The column's own rewrites (T0 examples, then T1 outputs) as demonstrations for the model."""

    from quwarts.core.represent.llm import demonstrations

    t1 = [(p, n) for p, n in s["map"].items() if s["tier"].get(p) == "t1"]
    return demonstrations(list(s["examples"]) + t1)


def _cells(conn, table: str, column: str) -> list[tuple[int, str]]:
    return conn.execute(f'SELECT rowid, "{column}" FROM "{table}" WHERE typeof("{column}") = \'text\'').fetchall()


def build(raw_db: Path, dest: Path, spec, fields: dict[str, Any], queries: dict[str, str], config: Config,
          caller: Callable | None = None, journal: Journal | None = None) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw_db, dest)
    manifest: dict[str, Any] = {"config": asdict(config), "name": config.name, "columns": {}, "joins": [], "groups": {}}
    if not config.t0:
        return manifest
    uses = grammar(spec, queries)
    tg = {k: t for k, t in targets(uses, fields, config.cardinality).items() if not t.numeric and t.uses > 0}
    conn = sqlite3.connect(dest)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    tg = {k: t for k, t in tg.items() if k[0] in tables and k[1] in {r[1] for r in conn.execute(f'PRAGMA table_info("{k[0]}")')}}
    journal = journal or Journal(dest.with_suffix(".llm.jsonl"))

    # T0 on every part; residual parts; T1 examples.
    state: dict[tuple[str, str], dict[str, Any]] = {}
    for key, t in tg.items():
        cells = _cells(conn, *key)
        raw_parts = Counter(p for _r, v in cells for p in parts(v))
        t0_map, examples, residual = {}, [], Counter()
        for p, n in raw_parts.items():
            new, rule = t0_part(p, t)
            t0_map[p] = new
            if rule in ("contains", "vocabulary") and new.casefold() in p.casefold():
                examples.append((p, new))
            if status(new, t) == "off":
                residual[p] = n
        state[key] = {"cells": cells, "raw_parts": raw_parts, "t0": t0_map, "examples": examples,
                      "residual": residual, "map": {}, "tier": {}}

    # T1: programs from T0's examples, per column.
    for key, s in state.items():
        s["keep"] = keep = T1.frequent_tokens(s["raw_parts"])
        progs = T1.learn(s["examples"], keep) if config.t1 else {}
        got = T1.apply(progs, list(s["residual"]), tg[key], keep) if progs else {}
        for p, new in got.items():
            s["map"][p], s["tier"][p] = new, "t1"
        s["programs"] = {c: [p.i, p.j, p.case] for c, p in progs.items()}
        s["coverage"] = T1.coverage(list(s["residual"]), progs, keep)

    # T2: router over columns, then the model on residual values.
    t2_stats: dict[str, Any] = {}
    if config.t2 != "none":
        plans, pending = [], {}
        for key, s in state.items():
            left = [p for p in s["residual"] if p not in s["map"]]
            if config.t2 == "cascade":
                classes = defaultdict(list)
                for p in sorted(left, key=lambda p: -s["residual"][p]):
                    classes[T1.pattern_class(p, s["keep"])].append(p)
                reps = [m for ms in classes.values() for m in ms[:T1.SUPPORT]]  # enough labels to learn a class program
                pending[key] = (left, reps, classes)
                cost = estimate_tokens(tg[key], reps, demos(s) if config.demos else None)
            else:
                pending[key] = (left, left, None)
                cost = estimate_tokens(tg[key], left, demos(s) if config.demos else None)
            rows = len(s["cells"])
            off_rows = sum(1 for _r, v in s["cells"] if any(q in left for q in parts(v)))
            plans.append(ColumnPlan(key, tg[key].uses, off_rows, rows, len(left), cost))
        chosen, planned = choose(plans, config.budget)
        t2_stats = {"planned_tokens": planned, "chosen": sorted(f"{a}.{b}" for a, b in chosen), "spent": 0, "calls": 0}
        for key in sorted(chosen):
            s = state[key]
            left, first, classes = pending[key]
            got, st = t2_normalize(tg[key], first, caller, journal, examples=demos(s) if config.demos else None)
            t2_stats["spent"] += st["tokens"]
            t2_stats["calls"] += st["calls"]
            for p, new in got.items():
                s["map"][p], s["tier"][p] = new, "t2"
            if classes is not None:  # cascade: programs from the model's labels generalize within a class
                ex = [(p, got[p]) for p in first if p in got and got[p].casefold() in p.casefold()]
                progs = T1.learn(ex + s["examples"], s["keep"])
                rest = [p for p in left if p not in s["map"]]
                for p, new in T1.apply(progs, rest, tg[key], s["keep"]).items():
                    s["map"][p], s["tier"][p] = new, "t2_program"
                s["cascade_programs"] = len(progs)
            s["t2"] = st

    # Materialize value rewrites.
    rep_rows = []
    for key, s in state.items():
        t = tg[key]
        changed = Counter()
        for rowid, v in s["cells"]:
            ps = parts(v)
            final = [s["map"].get(p, s["t0"].get(p, p)) for p in ps]
            new = combine(final, t)
            if new != v:
                tiers = {s["tier"].get(p, "t0") for p in ps if s["map"].get(p, s["t0"].get(p, p)) != p} or {"t0"}
                tier = "+".join(sorted(tiers))
                conn.execute(f'UPDATE "{key[0]}" SET "{key[1]}" = ? WHERE rowid = ?', (new, rowid))
                rep_rows.append((key[0], key[1], v, new, tier))
                changed[tier] += 1
        after = Counter(p for _r, v in _cells(conn, *key) for p in parts(v))
        manifest["columns"][f"{key[0]}.{key[1]}"] = {
            "uses": t.uses, "exact_uses": t.exact_uses, "vocabulary": len(t.vocabulary), "declared": t.declared,
            "multi": t.multi, "rows": len(s["cells"]), "distinct_parts": len(s["raw_parts"]),
            "residual_after_t0": len(s["residual"]),
            "residual_after_t1": len([p for p in s["residual"] if s["tier"].get(p) != "t1"]),
            "residual_final": sum(1 for p in after if status(p, t) == "off"),
            "off_share_before": round(sum(n for p, n in s["raw_parts"].items() if status(p, t) == "off") / max(1, sum(s["raw_parts"].values())), 3),
            "off_share_after": round(sum(n for p, n in after.items() if status(p, t) == "off") / max(1, sum(after.values())), 3),
            "cells_changed": dict(changed), "coverage": s["coverage"], "programs": s["programs"],
            "t2": s.get("t2"), "cascade_programs": s.get("cascade_programs")}

    # Entity resolution for joins, then folded duplicates of raw grouping columns.
    if config.er:
        for a, b, n in join_pairs(uses):
            if a[0] not in tables or b[0] not in tables:
                continue
            entity, reference = entity_side(conn, a, b)
            mapping, st = match_join(conn, entity, reference, caller, journal, config.er_model)
            changed = rewrite(conn, reference[0], reference[1], mapping)
            manifest["joins"].append({"entity": list(entity), "reference": list(reference), "queries": n,
                                      "mapped_surfaces": len(mapping), "cells_changed": changed, **st})
            rep_rows += [(reference[0], reference[1], k, v, "er") for k, v in mapping.items()]
    if config.group:
        for key, u in uses.items():
            if u.grouped and key in tg and not tg[key].declared:
                mapping = group_merges(conn, *key)
                changed = rewrite(conn, key[0], key[1], mapping)
                if mapping:
                    manifest["groups"][f"{key[0]}.{key[1]}"] = {"merged_surfaces": len(mapping), "cells_changed": changed}
                    rep_rows += [(key[0], key[1], k, v, "group") for k, v in mapping.items()]
    conn.execute('CREATE TABLE IF NOT EXISTS "__rep_map" (tbl TEXT, col TEXT, raw TEXT, view TEXT, tier TEXT)')
    conn.executemany('INSERT INTO "__rep_map" VALUES (?, ?, ?, ?, ?)', rep_rows)
    conn.commit()
    conn.close()
    manifest["t2"] = t2_stats
    manifest["cells_changed"] = dict(Counter(r[4] for r in rep_rows))
    return manifest

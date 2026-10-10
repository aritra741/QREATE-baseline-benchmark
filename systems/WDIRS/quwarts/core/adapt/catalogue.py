"""The per-column catalogue and the planner's decisions (results/experiments/why/SYSTEM_PLAN.md).

On a table's first on-demand request the planner (``drift_live``, ``QUWARTS_PLANNER=catalogue``):

1. takes every remaining schema column of the table (``C.design(..., robust=True)``: the benchmark attribute file's
   descriptions, the workload's usage phrases where it has used a column);
2. probes ten documents: each column alone, to learn where its stated values sit (the window), whether it is a coded
   absence, and its fill; then the frozen groups on the same documents, to learn its sensitivity to context;
3. plans the frozen prompts: a "head" prompt for the columns whose stated values sit in the first third of a
   document (neither lists nor coded absences), cut at their largest share, and whole-document prompts of at most
   ``MAX_FIELDS`` fields for the rest; a prompt is a byte string the stream never changes;
4. optionally declares a vocabulary for a column (``QUWARTS_VOCAB``: a JSON file {"table.column": [label, ...]},
   a schema input), and routes a stronger reader's second looks by a per-column repair rate (``repair.py``).

Components can be switched off one at a time with ``QUWARTS_PLANNER_OFF=unit,windows,vocab,repair`` (ablations).
"""

from __future__ import annotations

import json
import os
import statistics as S
from dataclasses import replace
from pathlib import Path
from typing import Any

from quwarts.core.adapt import controller as C
from quwarts.core.router.comparator import is_null
from quwarts.core.router.context_probe import FieldSpec

PROBE_DOCS = int(os.environ.get("QUWARTS_PROBE_DOCS", 10))
MAX_FIELDS = int(os.environ.get("QUWARTS_MAX_FIELDS", 16))
HEAD_SHARE = float(os.environ.get("QUWARTS_HEAD_SHARE", 0.35))
OFF = frozenset(x for x in os.environ.get("QUWARTS_PLANNER_OFF", "").split(",") if x)
assert OFF <= {"unit", "windows", "vocab", "repair"}, OFF
VOCAB = json.loads(Path(os.environ["QUWARTS_VOCAB"]).read_text()) if os.environ.get("QUWARTS_VOCAB") and "vocab" not in OFF else {}


def kind_of(f: FieldSpec) -> str:
    if f.value_type in ("int", "float"):
        return "number"
    if {x.lower() for x in f.choices} == {"yes", "no"}:
        return "yes/no"
    if f.value_type.startswith("multi") or f.multi_choice:
        return "list"
    return "category" if f.choices else "free text"


def norm(v) -> str:
    if isinstance(v, list):
        v = " || ".join(str(x) for x in v)
    return " ".join(str(v).strip().lower().split()) if v is not None else ""


def num_forms(v: str) -> list[str]:
    try:
        f = float(v.replace(",", ""))
    except ValueError:
        return [v]
    forms = {v, f"{f:g}", f"{int(f)}" if f == int(f) else f"{f}"}
    if f == int(f) and abs(f) >= 1000:
        forms.add(f"{int(f):,}")
    return sorted(forms)


def position_of(text_l: str, value) -> float | None:
    """Relative position of the first verbatim occurrence of the value (any item of a list; numbers in any common
    form), or None when it is not stated."""
    if is_null(value):
        return None
    items = [x.strip() for x in str(value).split("||")] if "||" in str(value) else [str(value)]
    best = None
    for it in items:
        for form in num_forms(it):
            f = norm(form)
            if len(f) < 2:
                continue
            i = text_l.find(f)
            if i >= 0:
                p = i / max(1, len(text_l))
                best = p if best is None else min(best, p)
    return best


def schema_fields(spec, seen: dict[str, str], table: str) -> dict[str, FieldSpec]:
    """Every schema column of the table, with the benchmark's description and the workload's usage phrase where it
    has used the column (``C.design`` with the robust option); vocabularies declared through QUWARTS_VOCAB become
    the column's allowed values."""
    fields, _ = C.design(spec, seen, robust=True)
    out = {}
    for k, f in fields.items():
        if not k.startswith(table + "."):
            continue
        if k in VOCAB and VOCAB[k] and kind_of(f) != "list":
            f = replace(f, choices=tuple(VOCAB[k]))
        out[k] = f
    return out


def probe_docs(names: list[str], n: int = PROBE_DOCS) -> list[str]:
    """A fixed sample of the table's documents (evenly spaced in name order: deterministic, no labels)."""
    names = sorted(names)
    if len(names) <= n:
        return names
    step = len(names) / n
    return [names[int(i * step)] for i in range(n)]


def column_stats(alone: dict[str, dict[str, Any]], grouped: dict[str, dict[str, Any]], texts: dict[str, str],
                 fields: dict[str, FieldSpec], table: str) -> dict[str, dict[str, Any]]:
    """Per column from the probe: fill alone and in the group, sensitivity (share of documents whose value differs
    between the two), grounding and position of the lone values, the window share with its exemptions."""
    out = {}
    for col, f in fields.items():
        a = col.split(".", 1)[1]
        av = {d: v.get(a) for d, v in alone.items() if a in v}
        gv = {d: v.get(a) for d, v in grouped.items() if a in v}
        both = [d for d in av if d in gv]
        filled = [d for d, v in av.items() if not is_null(v)]
        positions = [p for d in filled for p in [position_of(texts[d], av[d])] if p is not None]
        kind = kind_of(f)
        n_av = max(1, len(av))
        st = {"column": col, "kind": kind, "probe_docs": len(av),
              "fill_alone": round(len(filled) / n_av, 3),
              "fill_group": round(sum(not is_null(v) for v in gv.values()) / max(1, len(gv)), 3) if gv else None,
              "sensitivity": round(S.mean(norm(av[d]) != norm(gv[d]) for d in both), 3) if both else None,
              "grounded": round(len(positions) / max(1, len(filled)), 3) if filled else None,
              "stated": len(positions),
              "position_max": round(max(positions), 3) if positions else None,
              "absence_coded": bool(filled) and len(positions) < len(filled) / 3}
        share, why = 1.0, None
        if "windows" in OFF:
            why = "windows off"
        elif kind == "list":
            why = "list"
        elif st["absence_coded"]:
            why = "coded absence"
        elif len(positions) < 3:
            why = "fewer than three stated values"
        else:
            share = min(1.0, max(0.1, round(max(positions) + 0.05, 2)))
            if share > HEAD_SHARE:
                share, why = 1.0, f"values sit beyond the first {HEAD_SHARE:.0%}"
        st["share"], st["whole_document_because"] = share, why
        out[col] = st
    return out


def plan_groups(attrs: list[str], stats: dict[str, dict[str, Any]], table: str,
                narrow: list[list[str]] | None = None) -> list[dict[str, Any]]:
    """The frozen prompts: one head prompt for the windowed columns (cut at their largest share), the narrow prompts
    (columns the whole group under-fills, see ``context_hurt``), and whole-document prompts of at most MAX_FIELDS
    for the rest. Fields are in name order; a prompt never changes afterwards."""
    attrs = sorted(attrs)
    head = [a for a in attrs if stats.get(f"{table}.{a}", {}).get("share", 1.0) < 1.0]
    in_narrow = {a for g in (narrow or []) for a in g}
    whole = [a for a in attrs if a not in head and a not in in_narrow]
    groups = []
    if head:
        groups.append({"attributes": head, "share": max(stats[f"{table}.{a}"]["share"] for a in head)})
    for g in narrow or []:
        groups.append({"attributes": sorted(g), "share": 1.0, "narrow": True})
    for i in range(0, len(whole), MAX_FIELDS):
        groups.append({"attributes": whole[i:i + MAX_FIELDS], "share": 1.0})
    return groups


def context_hurt(stats: dict[str, dict[str, Any]], table: str, attrs: list[str]) -> list[str]:
    """Columns the whole-document group under-fills: filled on at least 30% of the probe documents alone, on fewer
    than half as many in the group, and with the lone values mostly stated in the document (so the group loses
    stated values, not inventions). The determined-context rule that fixed DocETL (I3b), per column."""
    out = []
    for a in attrs:
        st = stats.get(f"{table}.{a}", {})
        fa, fg, gr = st.get("fill_alone") or 0.0, st.get("fill_group") or 0.0, st.get("grounded") or 0.0
        if st.get("share", 1.0) >= 1.0 and fa >= 0.3 and fg < 0.5 * fa and gr >= 0.5:
            out.append(a)
    return sorted(out)

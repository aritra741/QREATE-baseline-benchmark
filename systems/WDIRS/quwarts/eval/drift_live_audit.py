"""Checks of the fixed-question drift levels that need no GPU. Run them before a long run.

    # 1. the pipeline against an extractor whose answer for a (document, field) never depends on the prompt
    #    (tests/oracle_ollama.py): every level must score the same; what may differ is listed with its cause
    bash systems/WDIRS/quwarts/scripts/chpc/audit_oracle.sh cspaper,player
    # 2. the design itself: nested levels, kept columns, no usage phrase built from a withheld query
    python -m quwarts.eval.drift_live_audit --design
    # 3. the results of any run (a real one too): which queries differ between levels, and why
    python -m quwarts.eval.drift_live_audit --levels cspaper,player

Expected with the oracle extractor: identical scores at every level except for queries whose served data differs
because of (a) documents a scoped patch left unread (they cannot change the answer: the score is the same) or
(b) the representation layer, which knows the anticipated queries' constants at build time (a real, small
effect of anticipation). Anything else is a bug.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3

from quwarts.core.adapt import controller as C
from quwarts.eval import drift_live as L
from quwarts.eval import drift_run as R

LEVELS = (0, 25, 50, 75, 100)


def streams(corpus: str, axis: str = "attribute") -> dict[int, dict[str, dict]]:
    out = {}
    for p in LEVELS:
        f = L.folder(corpus) / "streams" / f"{L.FIXED}-{axis}_{p}.jsonl"
        if f.exists():
            out[p] = {r["qid"]: r for r in map(json.loads, f.open())}
    return out


def view(corpus: str, axis: str, p: int, pos: int):
    return L.scratch(corpus) / f"{L.FIXED}-{axis}_{p}" / "views" / f"{pos:03d}.db"


def causes(corpus: str, axis: str, qid: str, S) -> dict[tuple[str, str], list[int]]:
    """Why a query's served data differs from level 0: per (column, kind), the levels. Needs the kept views
    (QUWARTS_KEEP_VIEWS=1 during the run)."""

    ctx = R.context(corpus)
    tables, cols = R.referenced(ctx.catalog[qid])
    out: dict[tuple[str, str], list[int]] = {}
    base = S[min(S)]
    for p in sorted(S):
        if p == min(S) or S[p][qid]["digest"] == base[qid]["digest"]:
            continue
        va, vb = view(corpus, axis, min(S), base[qid]["pos"]), view(corpus, axis, p, S[p][qid]["pos"])
        if not (va.exists() and vb.exists()):
            out.setdefault(("?", "views not kept"), []).append(p)
            continue
        A, B = sqlite3.connect(va), sqlite3.connect(vb)
        for t in tables:
            have = [x[1] for x in A.execute(f'PRAGMA table_info("{t}")')]
            use = [x for x in have if x.lower() in cols or x.lower().removesuffix("__canonical") in cols]
            sel = f'SELECT {", ".join(chr(34) + u + chr(34) for u in use)} FROM "{t}" ORDER BY rowid'
            for x, y in zip(A.execute(sel).fetchall(), B.execute(sel).fetchall()):
                for u, a, b in zip(use, x, y):
                    if a != b:
                        kind = ("unread (outside a patch's scope)" if b is None else
                                "represented differently" if a is not None else "empty at the first level")
                        out.setdefault((f"{t}.{u}", kind), [])
                        if p not in out[(f"{t}.{u}", kind)]:
                            out[(f"{t}.{u}", kind)].append(p)
    return out


def levels(corpora: list[str], axis: str = "attribute", explain: bool = True) -> None:
    for c in corpora:
        S = streams(c, axis)
        if not S:
            print(f"{c}: no {L.FIXED} results")
            continue
        qs = list(S[min(S)])
        moved = [q for q in qs if len({round(S[p][q]["benchmark"], 6) for p in S}) > 1]
        data = [q for q in qs if len({S[p][q]["digest"] for p in S}) > 1]
        mean = {p: round(sum(r["benchmark"] for r in S[p].values()) / len(S[p]), 3) for p in S}
        print(f"{c}: accuracy {mean} | queries {len(qs)} | score differs across levels {len(moved)} | served data differs {len(data)}")
        patches = {p: sum(r["action"] == "patch" for r in S[p].values()) for p in S}
        docs = {p: sum(r["docs_read"] for r in S[p].values()) for p in S}
        print(f"   patches {patches}  documents read {docs}")
        for q in data if explain else []:
            why = causes(c, axis, q, S)
            print(f"   {q[:58]:58s} scores {[round(S[p][q]['benchmark'], 3) for p in S]}")
            for (col, kind), ps in sorted(why.items()):
                print(f"      {col}: {kind} at {sorted(ps)}")


def design() -> int:
    problems = 0
    for c in L.ALL_CORPORA:
        ctx = R.context(c)
        for axis in ("attribute", "attribute_pool"):  # the axes with column levels (see drift_live.plan)
            d = L.fixed_design(c, axis)
            ps = sorted(int(p) for p in d["levels"])
            ant = {p: set(d["levels"][str(p)]["anticipated"]) for p in ps}
            spec = L.supplement_spec(c, axis)
            issues = []
            if not all(ant[b] <= ant[a] for a, b in zip(ps, ps[1:])):
                issues.append("withheld sets not nested")
            if not all(spec["kept"][b] <= spec["kept"][a] for a, b in zip(ps, ps[1:])):
                issues.append("kept columns do not shrink with the level")
            if spec["kept"][100]:
                issues.append("level 100 keeps extra columns")
            new = {tuple(x.split(".", 1)) for x in d.get("new_columns", [])}
            shares = []
            for p in ps:
                lvl = d["levels"][str(p)]
                missing = {tuple(x.split(".", 1)) for x in lvl.get("missing_columns", [])}
                if new and spec["kept"][p] != new - missing:
                    issues.append(f"level {p}: build keeps {len(spec['kept'][p])} columns, design says {len(new - missing)}")
                if not {tuple(x.split(".", 1)) for x in lvl.get("withheld_columns", [])} <= missing:
                    issues.append(f"level {p}: a withheld column is still in the build")
                # every unanticipated query uses a missing column, and no anticipated query does
                uses = lambda q: {(t, a) for t, aa in C.query_attributes(ctx.spec, q, ctx.catalog[q], {**ctx.w0, q: ctx.catalog[q]}).items() for a in aa}  # noqa: E731
                if any(not (uses(q) & missing) for q in lvl["withheld"]) or any(uses(q) & missing for q in lvl["anticipated"]):
                    issues.append(f"level {p}: anticipated/unanticipated split disagrees with the missing columns")
                shares.append(f"{p}%: {len(missing)}/{len(new)} cols, {100 * lvl.get('queries_unanticipated_share', 0):.0f}% queries")
            if len({s.split(': ')[1] for s in shares}) < len(shares):
                issues.append("two levels have the same drift")
            norm = lambda x: re.sub(r"[^a-z0-9]+", "", x.lower())  # noqa: E731
            for key, f in spec["fields"].items():
                t, a = key.split(".")
                keep = [p for p in ps if (t, a) in spec["kept"][p]]
                if keep != [p for p in ps if p <= max(keep)]:
                    issues.append(f"{key} kept at non-contiguous levels {keep}")
                allowed = set()
                for q in set.intersection(*[ant[p] for p in keep]):
                    allowed |= {norm(x) for x in re.findall(r"'([^']*)'", ctx.catalog[q])}
                for lit in re.findall(r"'([^']*)'", f.usage or ""):
                    if norm(lit) not in allowed:
                        issues.append(f"{key}: usage phrase constant {lit!r} not from a query anticipated wherever it is kept")
            problems += bool(issues)
            print(f"{c:8s} {axis:14s} test {len(d['test']):3d}, new columns {len(spec['fields']):2d}: "
                  + ("ok" if not issues else "; ".join(issues)) + "\n      " + " | ".join(shares))
    print("design problems:", problems)
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels")
    ap.add_argument("--axis", default="attribute")
    ap.add_argument("--design", action="store_true")
    a = ap.parse_args(argv)
    if a.design:
        design()
    if a.levels:
        levels(a.levels.split(","), a.axis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

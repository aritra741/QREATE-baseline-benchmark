"""I6 and I7 inputs (RESEARCH_DEPTH.md): the label contract and the per-column read windows, both from data the
system has without gold at the time of the patch, except where stated.

    python -m quwarts.eval.exp_contract contract   # results/experiments/I6-contract/<corpus>.json (gold vocabulary: an oracle)
    python -m quwarts.eval.exp_contract windows    # results/experiments/I7-windows/<corpus>.json (label-free)

contract: for every GROUP BY column of the test queries that is outside the build at 100% drift, the set of labels
gold uses (when at most 40 and fewer than half the rows: names are not a vocabulary), in gold's own spelling, unless
the field already declares a list that covers 95% of gold's rows. An oracle: the workload would have to declare these; the run measures what declaring them is worth.
windows: for every column outside the build, the 90th percentile of the relative position in the document of the
7B's own served value when it is stated verbatim there (the recorded run, no gold), as the share of the document a
patch reads for that column; whole documents where fewer than 10 values are stated or the share is above 0.9.
"""

from __future__ import annotations

import json
import sqlite3
import statistics as S
import sys
from collections import Counter, defaultdict
from pathlib import Path

from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPLAY_SCRATCH, gold_by_doc, is_null
from quwarts.eval.exp_context import LIVE, fields_of
from quwarts.eval.exp_open import HOME_SCRATCH, column_values, lookup
from quwarts.eval.exp_transfer import kind_of
from quwarts.eval.exp_workload import found, norm, num_forms

CORPORA = ["cspaper", "player", "art", "med", "legal"]


def new_columns(c: str) -> list[str]:
    return json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())["new_columns"]


def label(v) -> str | None:
    """A label as a GROUP BY compares it: numbers as numbers, text lowercased and trimmed."""
    s = norm(v)
    if not s:
        return None
    try:
        return repr(round(float(s.replace(",", "")), 6))
    except ValueError:
        return s


def contract() -> dict:
    groups = json.loads((EXP / "why" / "groups.json").read_text())
    cols = sorted({(r["corpus"], r["column"]) for r in groups["distinct"]})
    out_dir = EXP / "I6-contract"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for c in CORPORA:
        fields = fields_of(c)
        gold = gold_by_doc(c)
        new = set(new_columns(c))
        contract_c, rows = {}, []
        for cc, col in cols:
            if cc != c or col not in fields:
                continue
            t, a = col.split(".", 1)
            f = fields[col]
            many = f.value_type.startswith("multi") or f.multi_choice
            spelled, counts = {}, Counter()
            n_rows = 0
            for d, g in gold.get(t, {}).items():
                if a not in g or is_null(g[a]):
                    continue
                n_rows += 1
                items = [x.strip() for x in str(g[a]).split("||")] if many else [str(g[a]).strip()]
                for it in items:
                    k = label(it)
                    if k is None:
                        continue
                    counts[k] += 1
                    spelled.setdefault(k, Counter())[it] += 1
            kind = kind_of(f)
            declared = {label(x) for x in f.choices}
            covered = sum(n for k, n in counts.items() if k in declared) / max(1, sum(counts.values()))
            vocab = len(counts)
            why = None
            if col not in new:
                why = "in the build"
            elif kind == "number":
                why = "numeric"
            elif vocab > 40 or vocab >= 0.5 * n_rows:
                why = f"{vocab} labels" if vocab > 40 else f"{vocab} labels for {n_rows} rows: identifiers, not a vocabulary"
            elif f.choices and covered >= 0.95:
                why = f"declared list covers {covered:.0%}"
            row = {"column": col, "kind": kind, "gold_rows": n_rows, "labels": vocab, "declared": len(f.choices),
                   "declared_covers": round(covered, 3), "top": [k for k, _ in counts.most_common(6)], "contract": why is None, "why_not": why}
            rows.append(row)
            if why is None:
                contract_c[col] = [spelled[k].most_common(1)[0][0] for k, _ in counts.most_common()]
        (out_dir / f"{c}.json").write_text(json.dumps(contract_c, indent=1))
        report[c] = {"columns_contracted": len(contract_c), "rows": rows}
        print(f"{c}: {len(contract_c)} columns contracted of {len(rows)} group-by columns")
        for r in rows:
            print(f"   {'*' if r['contract'] else ' '} {r['column']:34s} {r['kind']:9s} rows={r['gold_rows']:5d} labels={r['labels']:3d} "
                  f"declared={r['declared']:2d} covers={r['declared_covers']:.2f} {r['why_not'] or ''} {r['top'][:4]}")
    (out_dir / "report.json").write_text(json.dumps(report, indent=1))
    return report


def windows() -> dict:
    grounding = json.loads((EXP / "WHY" / "grounding" / "summary.json").read_text())["position"]
    out_dir = EXP / "I7-windows"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    for c in CORPORA:
        ctx = R.context(c)
        fields = fields_of(c)
        P = HOME_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        if not P.exists():
            P = REPLAY_SCRATCH / c / "fixed4-attribute_pool_100" / "master.db"
        texts: dict[tuple, str] = {}
        shares, rows = {}, []
        gold_p90 = {k: v["p90"] for k, v in grounding.get(c, {}).get("columns_detail", {}).items()}
        for col in new_columns(c):
            if col not in fields:
                continue
            t, a = col.split(".", 1)
            pv = column_values(P, t, a)
            if pv is None:
                continue
            pos = []
            for d, path in ctx.docs.get(t, {}).items():
                v = lookup(pv, d)
                if is_null(v):
                    continue
                if (t, d) not in texts:
                    texts[(t, d)] = read_document(Path(path)).lower()
                ok, p = found(texts[(t, d)], v)
                if ok and p is not None:
                    pos.append(p)
            pos.sort()
            p90 = pos[int(0.9 * len(pos))] if len(pos) >= 10 else None
            share = round(p90, 3) if p90 is not None and p90 <= 0.9 else 1.0
            share = max(share, 0.1) if share < 1.0 else 1.0
            if share < 1.0:
                shares[col] = share
            rows.append({"column": col, "kind": kind_of(fields[col]), "stated_served_values": len(pos),
                         "p90_served": round(p90, 3) if p90 is not None else None, "p90_gold": gold_p90.get(col), "share": share})
        (out_dir / f"{c}.json").write_text(json.dumps(shares, indent=1))
        both = [(r["p90_served"], r["p90_gold"]) for r in rows if r["p90_served"] is not None and r["p90_gold"] is not None]
        report[c] = {"columns": len(rows), "windowed": len(shares), "mean_share": round(S.mean(shares.values()), 3) if shares else 1.0,
                     "mean_abs_gap_served_vs_gold_p90": round(S.mean(abs(x - y) for x, y in both), 3) if both else None,
                     "rows": rows}
        print(f"{c}: {len(shares)} of {len(rows)} new columns windowed, mean share {report[c]['mean_share']}, "
              f"served-vs-gold p90 gap {report[c]['mean_abs_gap_served_vs_gold_p90']}")
        for r in rows:
            print(f"    {r['column']:34s} {r['kind']:9s} n={r['stated_served_values']:4d} p90={r['p90_served']} gold={r['p90_gold']} share={r['share']}")
    (out_dir / "report.json").write_text(json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    {"contract": contract, "windows": windows}[sys.argv[1]]()

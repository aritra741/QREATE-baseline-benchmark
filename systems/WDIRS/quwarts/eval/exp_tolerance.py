"""Per-answer accuracy at 0, 5, 10 and 20% relative error for numbers (text: case and outer spaces ignored).

Over every single-column I1 read (alone, plus 2, plus 6, reworded, with the condition): accuracy per tolerance,
overall and for each column whose correct answers are numbers, plus H7's agreement split at each tolerance.
No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_tolerance
"""

from __future__ import annotations

import json
from collections import defaultdict

from quwarts.core.adapt import catalogue as K
from quwarts.core.router.comparator import as_number, is_null
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_intervene import OUT
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_repeat import CORPORA, KINDS, _reads

TOLS = (0.0, 0.05, 0.10, 0.20)


def right(v, g, tol) -> bool:
    return is_null(v) if is_null(g) else (not is_null(v) and correct(v, g, tol))


def main() -> int:
    rows = []
    for c in CORPORA:
        reads = _reads(OUT / "qwen7b" / c / "reads.jsonl")
        gold = gold_by_doc(c)
        for (t, d, k, a), v in reads.items():
            if k in KINDS:
                g = (gold.get(t, {}).get(d) or {}).get(a)
                rows.append({"column": f"{t}.{a}", "doc": (t, d), "kind": k, "v": v, "g": g,
                             "numeric": not is_null(g) and as_number(g) is not None})
    out = {"answers": len(rows), "accuracy": {}, "numeric_answers": sum(r["numeric"] for r in rows)}
    for tol in TOLS:
        out["accuracy"][f"{tol:.0%}"] = round(sum(right(r["v"], r["g"], tol) for r in rows) / len(rows), 4)
    num = [r for r in rows if r["numeric"]]
    out["accuracy_numeric_answers"] = {f"{t:.0%}": round(sum(right(r["v"], r["g"], t) for r in num) / len(num), 4) for t in TOLS}
    by = defaultdict(list)
    for r in num:
        by[r["column"]].append(r)
    out["numeric_columns"] = {col: {"answers": len(v), **{f"{t:.0%}": round(sum(right(r["v"], r["g"], t) for r in v) / len(v), 3) for t in TOLS},
                                    "examples_counted_right_only_at_20%": [(r["v"], r["g"]) for r in v if right(r["v"], r["g"], 0.2) and not right(r["v"], r["g"], 0.1)][:3]}
                              for col, v in sorted(by.items(), key=lambda x: -len(x[1]))}
    # H7 at each tolerance: alone vs plus 2, correctness of the lone answer when the two agree or differ
    cell = defaultdict(dict)
    for r in rows:
        cell[(r["doc"], r["column"])][r["kind"]] = r
    out["H7_alone_vs_plus2"] = {}
    for tol in TOLS:
        ag, df = [], []
        for by_kind in cell.values():
            if "alone" in by_kind and "plus2" in by_kind:
                a = by_kind["alone"]
                (ag if K.norm(a["v"]) == K.norm(by_kind["plus2"]["v"]) else df).append(right(a["v"], a["g"], tol))
        out["H7_alone_vs_plus2"][f"{tol:.0%}"] = {"agree_correct": round(sum(ag) / len(ag), 3), "differ_correct": round(sum(df) / len(df), 3)}
    dest = OUT.parent / "WHY" / "tolerance"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

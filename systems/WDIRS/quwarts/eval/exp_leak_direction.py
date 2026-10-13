"""Direction of predicate leakage: when a query's condition is shown in the extraction prompt, do answers move toward
satisfying it?  Uses the saved I1 reads (kind ``alone`` and ``with_predicate``, same column, same document) and the
condition (``conjunct``) recorded with each predicate read.  For each pair: does the alone answer satisfy the
condition, does the with-condition answer, does the correct answer.  No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_leak_direction
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

from quwarts.core.adapt import catalogue as K
from quwarts.core.router.comparator import is_null
from quwarts.core.router.probes import parse_fields
from quwarts.eval.exp_analysis import gold_by_doc

ROOT = Path(__file__).resolve().parents[4] / "results" / "experiments" / "I1-context"
CORPORA = ["cspaper", "player", "art", "med", "legal"]


def answer(r: dict, attr: str):
    """The answer as the system reads it (code fences stripped, renamed keys matched back to the field)."""
    v = parse_fields(r["response"], r["attributes"]).get(attr)
    if isinstance(v, list):
        v = " || ".join(str(x) for x in v)
    return None if is_null(v) else v


def satisfies(conjunct: str, attr: str, value) -> bool:
    """Whether a one-row table holding ``value`` in ``attr`` passes the condition (SQLite, NUMERIC affinity so
    numbers compare as numbers; a blank is NULL, which passes no comparison)."""
    con = sqlite3.connect(":memory:")
    con.execute(f'CREATE TABLE t ("{attr}" NUMERIC)')
    con.execute("INSERT INTO t VALUES (?)", (None if value is None else str(value),))
    try:
        return con.execute(f"SELECT COUNT(*) FROM t WHERE {conjunct}").fetchone()[0] == 1
    except sqlite3.Error:
        return None
    finally:
        con.close()


def main() -> int:
    rows = []
    for c in CORPORA:
        f = ROOT / "qwen7b" / c / "reads.jsonl"
        if not f.exists():
            continue
        reads = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        alone = {(r["table"], r["doc"], r["focal"]): r for r in reads if r["kind"] == "alone"}
        gold = gold_by_doc(c)
        for r in reads:
            if r["kind"] != "with_predicate" or not r.get("conjunct"):
                continue
            key = (r["table"], r["doc"], r["focal"])
            if key not in alone:
                continue
            a = r["focal"]
            g = (gold.get(r["table"], {}).get(r["doc"]) or {}).get(a)
            g = None if is_null(g) else g
            sa, sp, sg = (satisfies(r["conjunct"], a, v) for v in (answer(alone[key], a), answer(r, a), g))
            if None in (sa, sp, sg):
                continue
            rows.append({"corpus": c, "column": f"{r['table']}.{a}", "conjunct": r["conjunct"],
                         "changed": K.norm(answer(alone[key], a)) != K.norm(answer(r, a)),
                         "alone": sa, "with": sp, "gold": sg})
    out = {"pairs": len(rows)}

    def summary(rs):
        n = len(rs)
        ch = [x for x in rs if x["changed"]]
        return {"pairs": n, "changed": len(ch),
                "pass_rate_alone": round(sum(x["alone"] for x in rs) / n, 3),
                "pass_rate_with_condition": round(sum(x["with"] for x in rs) / n, 3),
                "pass_rate_gold": round(sum(x["gold"] for x in rs) / n, 3),
                "changed_now_passes": sum((not x["alone"]) and x["with"] for x in ch),
                "changed_now_fails": sum(x["alone"] and not x["with"] for x in ch),
                "wrongly_admitted": sum((not x["alone"]) and x["with"] and not x["gold"] for x in rs),
                "wrongly_dropped": sum(x["alone"] and not x["with"] and x["gold"] for x in rs),
                "selection_errors_alone": sum(x["alone"] != x["gold"] for x in rs),
                "selection_errors_with_condition": sum(x["with"] != x["gold"] for x in rs)}
    out["all"] = summary(rows)
    by = defaultdict(list)
    for x in rows:
        by[x["column"]].append(x)
    out["columns"] = {k: {**summary(v), "conjunct": v[0]["conjunct"]} for k, v in sorted(by.items())}
    dest = ROOT.parent / "WHY" / "leak_direction"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["all"], indent=1))
    for k, v in out["columns"].items():
        print(f"{k:40s} n={v['pairs']:3d} pass alone {v['pass_rate_alone']:.2f} with {v['pass_rate_with_condition']:.2f} gold {v['pass_rate_gold']:.2f}  {v['conjunct'][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

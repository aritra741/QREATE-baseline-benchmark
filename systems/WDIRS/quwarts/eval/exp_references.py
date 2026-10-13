"""Reference levels for the deck's pass marks, from the I1 reads and their resend (exp_repeat).  No model calls.

H1  rank agreement of column instability between two kinds of prompt change, against
    - chance: the same agreement with the columns shuffled (95th percentile of |rho| over 2,000 shuffles);
    - repeat: the agreement of a column's instability with itself when every prompt is sent again (originals vs
      resends, same kind of change), the highest agreement the measurement allows;
    - a 90% range from resampling each column's documents (1,000 draws).
H3  how many columns gain or lose at least 5 points of accuracy between alone and another prompt, against the same
    count between the lone prompt and its own resend (what chance alone produces).
H7  share of correct answers when two answers agree vs differ: alone vs plus 2 (two prompts), and alone vs its own
    resend (same prompt).

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_references
"""

from __future__ import annotations

import json
import random
from collections import defaultdict

from quwarts.core.adapt import catalogue as K
from quwarts.core.router.comparator import is_null
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_intervene import OUT
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_repeat import CORPORA, _reads
from quwarts.eval.exp_why import spearman

OTHER = ("plus2", "plus6", "paraphrase")


def same(a, b) -> bool:
    return K.norm(a) == K.norm(b)


def right(v, g) -> bool:
    return is_null(v) if is_null(g) else (not is_null(v) and correct(v, g))


def load():
    """column -> list of per-document dicts {kind: (first send, resend)} plus the gold answer."""
    cols = defaultdict(list)
    for c in CORPORA:
        o = _reads(OUT / "qwen7b" / c / "reads.jsonl")
        r = _reads(OUT / "qwen7b-repeat-t01" / c / "reads.jsonl")
        gold = gold_by_doc(c)
        cells = defaultdict(dict)
        for (t, d, k, a), v in o.items():
            if (k == "alone" or k in OTHER) and (t, d, k, a) in r:
                cells[(t, d, a)][k] = (v, r[(t, d, k, a)])
        for (t, d, a), by in cells.items():
            if "alone" in by and all(k in by for k in OTHER):
                cols[f"{t}.{a}"].append({**by, "gold": (gold.get(t, {}).get(d) or {}).get(a)})
    return {k: v for k, v in cols.items() if len(v) >= 10}


def instability(docs, kind, send=0):
    """Share of documents whose lone answer differs from this kind's answer (send 0: first sends, 1: resends)."""
    return sum(not same(x["alone"][send], x[kind][send]) for x in docs) / len(docs)


def main() -> int:
    cols = load()
    names = sorted(cols)
    rng = random.Random(7)
    out = {"columns": len(names)}

    # H1
    pairs = [("plus2", "plus6"), ("plus2", "paraphrase"), ("plus6", "paraphrase")]
    h1 = {}
    for a, b in pairs:
        xa = [instability(cols[n], a) for n in names]
        xb = [instability(cols[n], b) for n in names]
        rho = spearman(xa, xb)
        null = sorted(abs(spearman(xa, rng.sample(xb, len(xb)))) for _ in range(2000))
        boot = []
        for _ in range(1000):
            ya, yb = [], []
            for n in names:
                s = [rng.choice(cols[n]) for _ in cols[n]]
                ya.append(instability(s, a)); yb.append(instability(s, b))
            boot.append(spearman(ya, yb))
        boot.sort()
        h1[f"{a} vs {b}"] = {"agreement": round(rho, 3), "range_90": [round(boot[50], 3), round(boot[949], 3)],
                             "chance_95": round(null[1899], 3)}
    # repeat level: the same kind of change measured twice (first sends vs resends)
    h1["repeat level (same change, measured twice)"] = {
        k: round(spearman([instability(cols[n], k, 0) for n in names], [instability(cols[n], k, 1) for n in names]), 3)
        for k in OTHER}
    out["H1"] = h1

    # H3: columns gaining or losing >= 5 points
    def acc(docs, kind, send=0):
        return sum(right(x[kind][send], x["gold"]) for x in docs) / len(docs)

    h3 = {}
    for k in OTHER:
        d = [acc(cols[n], k) - acc(cols[n], "alone") for n in names]
        h3[f"alone vs {k}"] = {"better alone": sum(x <= -0.05 for x in d), "better with the change": sum(x >= 0.05 for x in d)}
    d = [acc(cols[n], "alone", 1) - acc(cols[n], "alone", 0) for n in names]
    h3["alone vs its own resend (chance)"] = {"first send better": sum(x <= -0.05 for x in d), "resend better": sum(x >= 0.05 for x in d)}
    for k in OTHER:
        d = [acc(cols[n], k, 1) - acc(cols[n], k, 0) for n in names]
        h3[f"{k} vs its own resend (chance)"] = {"first send better": sum(x <= -0.05 for x in d), "resend better": sum(x >= 0.05 for x in d)}
    out["H3"] = h3

    # H7
    def agree_split(pairs_):
        ag = [r for s, r in pairs_ if s]
        df = [r for s, r in pairs_ if not s]
        return {"agree": {"answers": len(ag), "correct": round(sum(ag) / len(ag), 3)},
                "differ": {"answers": len(df), "correct": round(sum(df) / len(df), 3) if df else None}}

    allx = [x for n in names for x in cols[n]]
    out["H7"] = {
        "alone vs plus 2 (two prompts)": agree_split([(same(x["alone"][0], x["plus2"][0]), right(x["alone"][0], x["gold"])) for x in allx]),
        "alone vs its resend (same prompt)": agree_split([(same(x["alone"][0], x["alone"][1]), right(x["alone"][0], x["gold"])) for x in allx]),
    }
    dest = OUT.parent / "WHY" / "references"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

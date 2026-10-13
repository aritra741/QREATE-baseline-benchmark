"""Why does the decision to answer at all flip?  70% of answer changes between prompts are blank against filled
(exp_why_change).  For cells whose correct answer is written in the document, each cell's fill rate over the five
prompts (alone, plus 2, plus 6, reworded, usual set) is related to (a) how many times the answer is written in the
document, (b) how far into the document it first appears, (c) the document's length.  A cell "flips" when some prompts
answer and others leave it blank.  For cells whose correct answer is blank, the filled answers are checked: written in
the document or not.  No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_why_fill
"""

from __future__ import annotations

import json
import statistics as S
from collections import defaultdict
from pathlib import Path

from quwarts.core.adapt import catalogue as K
from quwarts.core.router.comparator import is_null
from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_live as D
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_why_change import fields_of

ROOT = Path(__file__).resolve().parents[4] / "results" / "experiments" / "I1-context"
KINDS = ("alone", "plus2", "plus6", "paraphrase", "natural")


def mentions(text: str, value) -> tuple[int, float | None]:
    """How many times the value (any list item, numbers in common forms) is written, and where it first appears."""
    vals = [x.strip() for x in str(value).split("||")] if "||" in str(value) else [str(value)]
    best_n, first = 0, None
    for v in vals:
        for form in K.num_forms(v):
            f = K.norm(form)
            if len(f) < 2:
                continue
            n = text.count(f)
            if n:
                best_n = max(best_n, n)
                p = text.find(f) / max(1, len(text))
                first = p if first is None else min(first, p)
    return best_n, first


def binned(rows, key, edges, labels):
    out = {}
    for lo, hi, lab in zip(edges[:-1], edges[1:], labels):
        sel = [r for r in rows if r[key] is not None and lo <= r[key] < hi]
        if sel:
            out[lab] = {"cells": len(sel), "flip_share": round(S.mean(r["flips"] for r in sel), 3),
                        "fill_rate": round(S.mean(r["fill_rate"] for r in sel), 3)}
    return out


def main() -> int:
    stated, blank_gold = [], []
    for c in ["cspaper", "player", "art", "med", "legal"]:
        f = ROOT / "qwen7b" / c / "reads.jsonl"
        if not f.exists():
            continue
        ctx = D.R.context(c)
        gold = gold_by_doc(c)
        by = defaultdict(dict)
        for line in f.read_text().splitlines():
            r = json.loads(line)
            if r["kind"] in KINDS:
                by[(r["table"], r["doc"], r["focal"])][r["kind"]] = fields_of(r).get(r["focal"])
        texts = {}
        for (t, d, a), ans in by.items():
            if len(ans) < 3:
                continue
            if (t, d) not in texts:
                texts[(t, d)] = read_document(Path(ctx.docs[t][d])).lower()
            text = texts[(t, d)]
            g = (gold.get(t, {}).get(d) or {}).get(a)
            filled = [not is_null(v) for v in ans.values()]
            row = {"corpus": c, "column": f"{t}.{a}", "fill_rate": sum(filled) / len(filled),
                   "flips": 0 < sum(filled) < len(filled), "doc_chars": len(text)}
            if is_null(g):
                fills = [v for v in ans.values() if not is_null(v)]
                row["filled_values_written_in_document"] = sum(K.position_of(text, v) is not None for v in fills)
                row["filled_values"] = len(fills)
                blank_gold.append(row)
                continue
            n, first = mentions(text, g)
            if n == 0:
                continue
            row.update({"mentions": n, "first_position": first})
            stated.append(row)
    out = {"stated_cells": len(stated), "flip_share_stated": round(S.mean(r["flips"] for r in stated), 3)}
    out["by_mentions"] = binned(stated, "mentions", [1, 2, 3, 5, 10, 10**9], ["1", "2", "3-4", "5-9", "10+"])
    out["by_first_position"] = binned(stated, "first_position", [0, 0.05, 0.2, 0.5, 1.01],
                                      ["first 5%", "5-20%", "20-50%", "last half"])
    out["by_doc_length"] = binned(stated, "doc_chars", [0, 5000, 15000, 40000, 10**9],
                                  ["under 5k chars", "5k-15k", "15k-40k", "over 40k"])
    # mentions within short and long documents, to separate the two
    for lab, lo, hi in (("documents under 15k chars", 0, 15000), ("documents of 15k chars or more", 15000, 10**9)):
        sel = [r for r in stated if lo <= r["doc_chars"] < hi]
        out[f"by_mentions, {lab}"] = binned(sel, "mentions", [1, 2, 5, 10**9], ["1", "2-4", "5+"])
    fv = sum(r["filled_values"] for r in blank_gold)
    out["correct_answer_blank"] = {"cells": len(blank_gold), "flip_share": round(S.mean(r["flips"] for r in blank_gold), 3),
                                   "filled_answers": fv,
                                   "filled_answers_written_in_document": sum(r["filled_values_written_in_document"] for r in blank_gold)}
    dest = ROOT.parent / "WHY" / "why_fill"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

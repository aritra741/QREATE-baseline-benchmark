"""What exactly changes when only the prompt changes?  For every (column, document) in the saved I1 reads, the answer
to the question asked alone is compared with the answer to the same question under each other prompt (plus 2, plus 6,
reworded, usual set).  Every pair that differs is put in the first matching category:

  blank vs filled        one prompt answered, the other left the cell blank
  copied from neighbour  the new answer equals (or is contained in) the answer the same prompt gave for another
                         question it asked
  same value, other form the two answers are the same value under the scorer's comparison or one contains the other
                         (case, punctuation, date precision, units)
  more or fewer items    lists: one answer's items are a subset of the other's
  other stated value     both answers are written in the document (a different candidate chosen)
  partly different list  lists sharing some items
  unstated value         at least one answer is not written in the document

The categories are then broken down by the correct answer (blank, written word for word, not word for word), and
for "other stated value" the document is searched for how many distinct values of that kind it states.  No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_why_change
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from quwarts.core.adapt import catalogue as K
from quwarts.core.router.comparator import is_null
from quwarts.core.router.probes import parse_fields
from quwarts.eval.exp_analysis import same_value
from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_live as D
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_open import correct

ROOT = Path(__file__).resolve().parents[4] / "results" / "experiments" / "I1-context"
OTHER = ("plus2", "plus6", "paraphrase", "natural")


def fields_of(r: dict) -> dict:
    """Answers as the system reads them (code fences stripped, renamed keys matched back to the fields)."""
    f = parse_fields(r["response"], r["attributes"])
    out = {}
    for k, v in f.items():
        if isinstance(v, list):
            v = " || ".join(str(x) for x in v)
        out[k] = None if is_null(v) else v
    return out


def items(v) -> set:
    return {K.norm(x) for x in str(v).split("||") if x.strip()}


def same(a, b) -> bool:
    na, nb = K.norm(a), K.norm(b)
    if same_value(a, b) or same_value(b, a):
        return True
    return len(na) >= 3 and len(nb) >= 3 and (na in nb or nb in na)


def category(a, b, other_fields: dict, text: str, is_list: bool) -> str:
    if is_null(a) != is_null(b):
        return "blank vs filled"
    for k, v in other_fields.items():
        if v is not None and K.norm(b) and (K.norm(b) == K.norm(v) or (len(K.norm(v)) >= 4 and K.norm(v) in K.norm(b) and not same(a, b))):
            return "copied from neighbour"
    if same(a, b):
        return "same value, other form"
    if is_list:
        ia, ib = items(a), items(b)
        if ia and ib and (ia < ib or ib < ia):
            return "more or fewer items"
    ga, gb = K.position_of(text, a) is not None, K.position_of(text, b) is not None
    if ga and gb:
        return "other stated value"
    if is_list and items(a) & items(b):
        return "partly different list"
    return "unstated value"


def main() -> int:
    kinds = {x["column"]: x["kind"] for x in json.loads((ROOT / "summary.json").read_text())["columns"]["qwen7b"]}
    pairs = []
    cells = []
    for c in ["cspaper", "player", "art", "med", "legal"]:
        f = ROOT / "qwen7b" / c / "reads.jsonl"
        if not f.exists():
            continue
        ctx = D.R.context(c)
        gold = gold_by_doc(c)
        by = defaultdict(dict)
        for line in f.read_text().splitlines():
            r = json.loads(line)
            if r["kind"] == "alone" or r["kind"] in OTHER:
                by[(r["table"], r["doc"], r["focal"])][r["kind"]] = fields_of(r)
        texts = {}
        for (t, d, a), reads in by.items():
            if "alone" not in reads:
                continue
            if (t, d) not in texts:
                texts[(t, d)] = read_document(Path(ctx.docs[t][d])).lower()
            text = texts[(t, d)]
            g = (gold.get(t, {}).get(d) or {}).get(a)
            gclass = ("correct answer is blank" if is_null(g) else
                      "correct answer written in the document" if K.position_of(text, g) is not None else
                      "correct answer not written word for word")
            is_list = kinds.get(f"{t}.{a}") == "list"
            alone = reads["alone"].get(a)
            cell_cats = []
            for k in OTHER:
                if k not in reads:
                    continue
                b = reads[k].get(a)
                if K.norm(alone) == K.norm(b):
                    continue
                others = {kk: vv for kk, vv in reads[k].items() if kk != a}
                cat = category(alone, b, others, text, is_list)
                right_a = correct(alone, g) if g is not None or True else None
                right_b = correct(b, g)
                pairs.append({"corpus": c, "column": f"{t}.{a}", "doc": d, "prompt": k, "category": cat,
                              "gold_class": gclass, "list": is_list, "alone": alone, "other": b, "gold": g,
                              "alone_right": right_a, "other_right": right_b,
                              "blank_side": (None if cat != "blank vs filled" else ("other prompt left it blank" if is_null(b) else "alone left it blank"))})
                cell_cats.append(cat)
            cells.append({"gold_class": gclass, "list": is_list, "unstable": bool(cell_cats), "categories": cell_cats})
    out = {"pairs_changed": len(pairs), "cells": len(cells)}
    cnt = Counter(p["category"] for p in pairs)
    out["category_share"] = {k: round(v / len(pairs), 3) for k, v in cnt.most_common()}
    by_g = defaultdict(Counter)
    tot_g = Counter()
    for p in pairs:
        by_g[p["gold_class"]][p["category"]] += 1
        tot_g[p["gold_class"]] += 1
    out["category_share_by_correct_answer"] = {g: {k: round(v / tot_g[g], 3) for k, v in by_g[g].most_common()} for g in by_g}
    # per cell: unstable share by correct answer, and the same with each category removed (what drives the gap?)
    gcells = defaultdict(list)
    for x in cells:
        gcells[x["gold_class"]].append(x)
    out["unstable_share_by_correct_answer"] = {g: round(sum(x["unstable"] for x in v) / len(v), 3) for g, v in gcells.items()}
    out["unstable_share_counting_only"] = {}
    for cat in cnt:
        out["unstable_share_counting_only"][cat] = {g: round(sum(cat in x["categories"] for x in v) / len(v), 3) for g, v in gcells.items()}
    # who is right when the answer changes
    right = defaultdict(Counter)
    for p in pairs:
        right[p["category"]]["alone right, other wrong" if p["alone_right"] and not p["other_right"] else
                             "alone wrong, other right" if p["other_right"] and not p["alone_right"] else
                             "both wrong" if not p["alone_right"] else "both right"] += 1
    out["correctness_by_category"] = {k: dict(v) for k, v in right.items()}
    blank = Counter(p["blank_side"] + " | " + p["gold_class"] for p in pairs if p["blank_side"])
    out["blank_vs_filled_detail"] = dict(blank.most_common())
    out["examples"] = {}
    for cat in cnt:
        ex = [p for p in pairs if p["category"] == cat][:6]
        out["examples"][cat] = [{k: p[k] for k in ("column", "prompt", "alone", "other", "gold")} for p in ex]
    dest = ROOT.parent / "WHY" / "why_change"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    (dest / "pairs.jsonl").write_text("\n".join(json.dumps(p, default=str) for p in pairs))
    print(json.dumps({k: v for k, v in out.items() if k != "examples"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

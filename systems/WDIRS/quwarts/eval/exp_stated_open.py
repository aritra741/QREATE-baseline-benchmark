"""Is instability concentrated in answers the document does not state?  Per (column, document) from the saved I1
reads: the cell is unstable if the answer to the question asked alone differs from the answer under any of the other
prompts (plus 2, plus 6, reworded, usual set).  Each cell is classed by its correct answer (blank in gold; stated
word for word in the document; given but not word for word) and, separately, by whether the model's own lone answer
appears word for word.  No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_stated_open
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from quwarts.core.adapt import catalogue as K
from quwarts.core.router.comparator import is_null
from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_live as D
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_leak_direction import answer
from quwarts.eval.exp_open import correct

ROOT = Path(__file__).resolve().parents[4] / "results" / "experiments" / "I1-context"
OTHER = ("plus2", "plus6", "paraphrase", "natural")


def main() -> int:
    cells = []
    kinds = {x["column"]: x["kind"] for x in json.loads((ROOT / "summary.json").read_text())["columns"]["qwen7b"]}
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
                by[(r["table"], r["doc"], r["focal"])][r["kind"]] = answer(r, r["focal"])
        texts = {}
        for (t, d, a), ans in by.items():
            if "alone" not in ans or not any(k in ans for k in OTHER):
                continue
            g = (gold.get(t, {}).get(d) or {}).get(a)
            if (t, d) not in texts:
                texts[(t, d)] = read_document(Path(ctx.docs[t][d])).lower()
            text = texts[(t, d)]
            alone = ans["alone"]
            unstable = any(K.norm(ans[k]) != K.norm(alone) for k in OTHER if k in ans)
            # a different value, not just a different wording: neither answer matches the other under the lenient
            # comparison used for scoring cells (blank against a value counts as different)
            def differs(x, y):
                if is_null(x) or is_null(y):
                    return is_null(x) != is_null(y)
                return not (correct(x, y) or correct(y, x))
            unstable_value = any(differs(ans[k], alone) for k in OTHER if k in ans)
            if is_null(g):
                gclass = "correct answer is blank"
            elif K.position_of(text, g) is not None:
                gclass = "correct answer written in the document"
            else:
                gclass = "correct answer not written word for word"
            mclass = ("model left it blank" if is_null(alone) else
                      "model's answer written in the document" if K.position_of(text, alone) is not None else
                      "model's answer not in the document")
            cells.append({"corpus": c, "column": f"{t}.{a}", "kind": "list" if kinds.get(f"{t}.{a}") == "list" else "single value", "unstable": unstable, "unstable_value": unstable_value, "gold_class": gclass,
                          "model_class": mclass, "right": (not is_null(g)) and correct(alone, g) or (is_null(g) and is_null(alone))})
    out = {"cells": len(cells)}
    for key in ("gold_class", "model_class"):
        grp = defaultdict(list)
        for x in cells:
            grp[x[key]].append(x)
        out[key] = {k: {"cells": len(v), "unstable_share": round(sum(x["unstable"] for x in v) / len(v), 3),
                        "different_value_share": round(sum(x["unstable_value"] for x in v) / len(v), 3),
                        "right_share": round(sum(x["right"] for x in v) / len(v), 3)} for k, v in sorted(grp.items())}
    grp = defaultdict(list)
    for x in cells:
        grp[x["kind"] + " | " + x["gold_class"]].append(x)
    out["kind_and_gold_class"] = {k: {"cells": len(v), "unstable_share": round(sum(x["unstable"] for x in v) / len(v), 3),
                                      "different_value_share": round(sum(x["unstable_value"] for x in v) / len(v), 3)}
                                  for k, v in sorted(grp.items())}
    dest = ROOT.parent / "WHY" / "stated_open"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

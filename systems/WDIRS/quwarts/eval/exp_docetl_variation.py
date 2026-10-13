"""Two post-hoc checks on DocETL's saved outputs (no model calls).

1. Does variation belong to the column in a second system?  DocETL extracts the columns a query needs, from every
   document, with a prompt written for that query; the same (document, column) is therefore read once per query
   that needs it. Per column: the share of document pairs-of-reads that disagree (normalized values; a blank is a
   value), against our system's instability of the same column (I1, Qwen 7B), its resend rate, and the column kind.
2. Why does DocETL leave fields empty?  Per read: is the answer empty, is the correct answer empty, is the correct
   answer written word for word in the document, the column kind, and the column's role in that query (grouped by,
   filtered on, aggregated, selected).

Sources: results/docetl_drift_ollama (the template workload) and results/docetl_realistic*_ollama (realistic
workloads), every <query>/table_<t>/pipeline_output.json whose query id is known.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python -m quwarts.eval.exp_docetl_variation
"""

from __future__ import annotations

import json
import os
import statistics as S
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from quwarts.core.adapt import catalogue as K
from quwarts.core.router.comparator import is_null
from quwarts.core.router.corpus_features import read_document
from quwarts.eval import drift_live as D
from quwarts.eval.exp_analysis import gold_by_doc
from quwarts.eval.exp_context import fields_of
from quwarts.eval.exp_profile import roles
from quwarts.eval.exp_tau import EXP
from quwarts.eval.exp_transfer import kind_of
from quwarts.eval.exp_why import spearman

CORPORA = ["cspaper", "player", "art", "med", "legal"]
ROOTS = ["docetl_drift_ollama", "docetl_realistic_ollama", "docetl_realistic_v2_ollama", "docetl_realistic_v3_ollama"]


def safe(qid: str) -> str:
    return qid.replace("/", "_").replace(":", "_").replace("#", "_")


def blank(v) -> bool:
    return is_null(v) or (isinstance(v, str) and v.strip() in ("", "-1", "Not found", "not found")) or v == -1


def catalogs(c: str) -> dict:
    """Every query id DocETL ran, with its SQL: the drift catalogue plus the realistic versions."""
    ctx = D.R.context(c)
    cat = dict(ctx.catalog)
    cat.update(ctx.w0)
    from quwarts.eval import realistic_queries as RQ

    for v in ("v1", "v2", "v3"):
        RQ.VERSION = v
        try:
            for qid, _q, sql in RQ.load(c):
                cat[qid] = sql
        except FileNotFoundError:
            pass
    RQ.VERSION = os.environ.get("QUWARTS_REALISTIC", "v1")
    return cat


def main() -> int:
    i1 = {x["column"]: x for x in json.loads((EXP / "I1-context" / "summary.json").read_text())["columns"]["qwen7b"]}
    resend = json.loads((EXP / "WHY" / "repeat" / "summary.json").read_text())
    out = {"columns": {}, "blank_reads": {}}
    reads_all = []
    for c in CORPORA:
        ctx = D.R.context(c)
        cat = catalogs(c)
        by_safe = {safe(q): q for q in cat}
        fields = fields_of(c)
        gdoc = gold_by_doc(c)
        texts = {}
        vals = defaultdict(lambda: defaultdict(list))  # column -> doc -> [value per query]
        for root in ROOTS:
            base = EXP.parent / root / c
            if not base.exists():
                continue
            for qdir in base.iterdir():
                qid = by_safe.get(qdir.name)
                if qid is None or not qdir.is_dir():
                    continue
                r = roles(cat[qid])
                for tdir in qdir.glob("table_*"):
                    t = tdir.name[len("table_"):]
                    f = tdir / "pipeline_output.json"
                    if not f.exists():
                        continue
                    for row in json.loads(f.read_text()):
                        d = str(row.get("doc_id"))
                        g = (gdoc.get(t, {}).get(d) or gdoc.get(t, {}).get(d.rsplit(".", 1)[0]) or {})
                        for a, v in row.items():
                            if a == "doc_id":
                                continue
                            col = f"{t}.{a}"
                            vals[col][d].append(None if blank(v) else K.norm(v))
                            role = ("grouped by" if col in r["grouped by"] else "filtered on" if col in r["filtered on"]
                                    else "aggregated" if col in r["aggregated"] else "selected or joined")
                            gv = g.get(a)
                            reads_all.append({"corpus": c, "column": col, "kind": kind_of(fields[col]) if col in fields else "other",
                                              "role": role, "empty": blank(v), "gold_empty": is_null(gv), "doc": d, "table": t, "gold": gv})
        for col, docs in vals.items():
            pairs = [(a, b) for d in docs.values() if len(d) >= 2 for a, b in combinations(d, 2)]
            if len(pairs) < 30:
                continue
            reads = [len(d) for d in docs.values()]
            mine = i1.get(col, {})
            out["columns"][f"{c}:{col}"] = {
                "kind": kind_of(fields[col]) if col in fields else "other", "documents": len(docs),
                "reads_per_document_median": S.median(reads),
                "docetl_disagreement": round(sum(a != b for a, b in pairs) / len(pairs), 3),
                "docetl_empty_share": round(sum(v is None for d in docs.values() for v in d) / sum(reads), 3),
                "ours_instability_I1": mine.get("mean_sensitivity")}
        # written-in-text for the correct answer, on a sample of blank-vs-filled reads (expensive: read the document)
        for r in reads_all:
            if r["corpus"] != c or r["gold_empty"] or "written" in r:
                continue
            key = (r["table"], r["doc"])
            if key not in texts:
                p = ctx.docs.get(r["table"], {}).get(r["doc"]) or ctx.docs.get(r["table"], {}).get(r["doc"] + ".txt")
                texts[key] = read_document(Path(p)).lower() if p else ""
            r["written"] = K.position_of(texts[key], r["gold"]) is not None if texts[key] else None
    # 1. column-level comparison
    cols = out["columns"]
    both = [v for v in cols.values() if v["ours_instability_I1"] is not None]
    out["agreement_with_ours"] = {"columns": len(both),
                                  "rank_correlation": round(spearman([v["docetl_disagreement"] for v in both], [v["ours_instability_I1"] for v in both]), 3) if len(both) >= 6 else None}
    kinds = defaultdict(list)
    for v in cols.values():
        kinds[v["kind"]].append(v["docetl_disagreement"])
    out["docetl_disagreement_by_kind"] = {k: {"columns": len(x), "mean": round(S.mean(x), 3)} for k, x in kinds.items()}
    # 2. empty answers
    def rate(sel):
        return {"reads": len(sel), "empty_share": round(sum(r["empty"] for r in sel) / len(sel), 3)} if sel else None
    filled = [r for r in reads_all if not r["gold_empty"]]
    out["blank_reads"] = {
        "all reads, correct answer filled": rate(filled),
        "correct answer empty": rate([r for r in reads_all if r["gold_empty"]]),
        "correct answer written word for word": rate([r for r in filled if r.get("written") is True]),
        "correct answer not written word for word": rate([r for r in filled if r.get("written") is False]),
        "by kind": {k: rate([r for r in filled if r["kind"] == k]) for k in sorted({r["kind"] for r in filled})},
        "by role in the query": {k: rate([r for r in filled if r["role"] == k]) for k in sorted({r["role"] for r in filled})},
        "by corpus": {c: rate([r for r in filled if r["corpus"] == c]) for c in CORPORA}}
    dest = EXP / "WHY" / "docetl_variation"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({k: v for k, v in out.items() if k != "columns"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

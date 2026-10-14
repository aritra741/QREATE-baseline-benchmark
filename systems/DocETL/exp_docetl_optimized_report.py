"""Scores of the DocETL optimizer runs, rebuilt from their saved outputs, next to plain DocETL and our system (Qwen).

For every results/docetl_optimized/<optimizer>-qwen/<corpus>/<query>/ the tables are rebuilt from each
table_<t>/pipeline_output.json exactly as exp_docetl_optimized does (clean, one row per document, first non-empty value
per field), the query's database is built and scored; the plan's steps come from plan_used.yaml and the executing
model's tokens from the run's log. Compared with: plain DocETL on Qwen (as run on the realistic workload; with the type
fix where that arm exists; split documents where that arm exists) and our system (realistic run).

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired ~/venvs/quwarts/bin/python systems/DocETL/exp_docetl_optimized_report.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> int:
    import run_docetl_drift as RD
    import yaml
    from quwarts.eval import drift_live as D
    from quwarts.eval.exp_docetl_variation import catalogs
    from quwarts.eval.exp_tau import EXP, TAUS, score_multi

    repo = RD.ROOT
    base = repo / "results" / "docetl_optimized"
    logs = EXP / "logs" / "opt"
    out = {}
    for run in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("smoke")):
        opt = run.name.split("-")[0]
        for cdir in sorted(p for p in run.iterdir() if p.is_dir()):
            c = cdir.name
            ctx = D.R.context(c)
            cat = catalogs(c)
            for qdir in sorted(p for p in cdir.iterdir() if p.is_dir() and p.name.startswith("real_")):
                qid = next((q for q in cat if RD.safe(q) == qdir.name), None)
                if qid is None:
                    continue
                sql = cat[qid]
                ctx.catalog.setdefault(qid, sql)
                fields, reads = D.C.design(ctx.spec, {qid: sql})
                tables, numeric, plans, complete = {}, {}, {}, True
                log = logs / f"{opt}_{c}_{qid.split('#')[1]}.log"
                if not (log.exists() and "score@20" in log.read_text(errors="ignore")):  # the run has not finished
                    out.setdefault(c, {}).setdefault(qid, {})[opt] = {"incomplete": True}
                    continue
                for r in reads:
                    if r.table not in ctx.names or not r.attributes:
                        continue
                    t, attrs = r.table, list(r.attributes)
                    po = qdir / f"table_{t}" / "pipeline_output.json"
                    if not po.exists():
                        complete = False
                        break
                    got = {}
                    for row in RD.clean(json.loads(po.read_text()), attrs):
                        d = row.get("doc_id")
                        cur = got.setdefault(d, {"doc_id": d})
                        for x in attrs:
                            if cur.get(x.lower()) in (None, "", -1) and row.get(x.lower()) not in (None, "", -1):
                                cur[x.lower()] = row.get(x.lower())
                    tables[t] = list(got.values())
                    numeric[t] = {x.lower() for x in attrs if getattr(fields.get(f"{t}.{x}"), "value_type", "str") in ("int", "float")}
                    pu = qdir / f"table_{t}" / "plan_used.yaml"
                    plans[t] = [f"{o.get('type')}:{o.get('name')}" for o in (yaml.safe_load(pu.read_text()) or {}).get("operations", [])] if pu.exists() else None
                if not complete:
                    out.setdefault(c, {}).setdefault(qid, {})[opt] = {"incomplete": True}
                    continue
                db = RD.build_db(c, sql, tables, numeric, cdir / "db" / f"{qdir.name}.db")
                sc = score_multi(c, [(qid, db)])[qid]
                log = logs / f"{opt}_{c}_{qid.split('#')[1]}.log"
                tok = None
                if log.exists():
                    m = re.search(r"([0-9.]+)M tok \(executing model\)", log.read_text(errors="ignore"))
                    tok = float(m.group(1)) if m else None
                out.setdefault(c, {}).setdefault(qid, {})[opt] = {"score": {f"{t:.0%}": sc.get(t) for t in TAUS}, "plans": plans,
                                                                  "rows": {t: len(v) for t, v in tables.items()}, "qwen_tokens_M": tok}
    # baselines on Qwen
    for c, qs in out.items():
        plain = json.loads((repo / "results" / "docetl_realistic_ollama" / c / "per_query.json").read_text())
        swap = json.loads((EXP / "WHY" / "swap" / f"realistic_{c}.json").read_text())[c]["per_query"]
        arms = {}
        for arm in ("strfix", "chunked"):
            p = repo / "results" / "docetl_arms" / arm / c / "per_query.json"
            if p.exists():
                arms[arm] = json.loads(p.read_text())
        for qid, r in qs.items():
            r["plain DocETL (as run)"] = {"20%": swap.get(qid, {}).get("docetl"), "tokens_M": round((plain.get(qid, {}).get("prompt_tokens", 0) + plain.get(qid, {}).get("completion_tokens", 0)) / 1e6, 2)}
            for arm, d in arms.items():
                if qid in d:
                    r[f"DocETL {arm}"] = {"score": d[qid]["score"], "tokens_M": round((d[qid]["prompt_tokens"] + d[qid]["completion_tokens"]) / 1e6, 2)}
            r["ours"] = {"20%": swap.get(qid, {}).get("ours")}
    dest = EXP / "WHY" / "docetl_optimizer"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    for c, qs in out.items():
        for qid, r in sorted(qs.items()):
            def s20(x):
                v = (x or {}).get("score", x or {}).get("20%") if isinstance(x, dict) else None
                return f"{v:.3f}" if isinstance(v, (int, float)) else "-"
            print(f"{qid:20s} plain {s20(r.get('plain DocETL (as run)'))}  typefix {s20(r.get('DocETL strfix'))}  split {s20(r.get('DocETL chunked'))}  "
                  f"v1 {s20(r.get('v1'))}  moar {s20(r.get('moar'))}  ours {s20(r.get('ours'))}  | v1 plan {(r.get('v1') or {}).get('plans')}  moar plan {(r.get('moar') or {}).get('plans')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

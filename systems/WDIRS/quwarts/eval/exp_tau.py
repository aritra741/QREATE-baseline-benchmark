"""Query scores at 0, 5, 10 and 20% value tolerance (structure F2 x cell F1@tau, the drift runs' metric).

The cell tolerance is the benchmark's: a numeric result cell counts as right when its error is at most tau of the
range of the correct values in that result column (aggregation_metrics._numeric_range_err); text cells must match.
Every score so far used tau = 0.20. Rescored here, on the test queries of the fully drifted workload:
  - DocETL: the database it produced for each query (results/docetl_drift_ollama/<corpus>/db);
  - our system (V3, V3-rep1, V3-rep2) and our system without re-reads (V3-ablate-repair, -rep2): the run's final
    table (exp_cause.final_view). The recorded scores used the table at each query's position in the stream; the
    script reports both at 20% so the difference is visible.
No model calls.

    PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python -m quwarts.eval.exp_tau <scratch dir> [corpus ...]
"""

from __future__ import annotations

import json
import sqlite3
import statistics as S
import sys
from pathlib import Path

from quwarts.eval import drift_live as D
from quwarts.eval.exp_cause import final_view

TAUS = (0.0, 0.05, 0.10, 0.20)
EXP = Path(__file__).resolve().parents[4] / "results" / "experiments"
DOCETL = EXP.parent / "docetl_drift_ollama"
OURS = {"our system": ["V3", "V3-rep1", "V3-rep2"], "our system without re-reads": ["V3-ablate-repair", "V3-ablate-repair-rep2"]}


def safe(qid: str) -> str:
    """run_docetl_drift.safe: the file name of a query's database."""
    return qid.replace("/", "_").replace(":", "_").replace("#", "_")


def score_multi(corpus: str, items: list[tuple[str, Path]]) -> dict[str, dict[float, float]]:
    """Per query: structure F2 x cell F1 at every tau, on the official SQL path of drift_run.Scorer('benchmark')."""
    from quwarts.core.pipeline import official_sql
    from quwarts.eval.drift_run import predicates
    from quwarts.experiments.player_case80 import execute
    from spp.aggregation_metrics import (MetricConfig, evaluate_aggregation_tables, gold_table_from_sql,
                                         json_ready_metrics, predicted_table_from_rows, schema_from_sql)
    from spp.config_grid import _build_in_memory_db

    R = D.R
    ctx = R.context(corpus)
    gold, _ = R.Scorer(corpus).gold()
    gold_conn = _build_in_memory_db(gold)
    config = MetricConfig(tau_sweep=TAUS)
    preds = predicates(corpus)
    out = {}
    for qid, db in items:
        sql = ctx.catalog[qid]
        res = {t: 0.0 for t in TAUS}
        try:
            psql = official_sql(sql, str(db), preds, query_id=qid)
            gold_rows = execute(gold_conn, sql)
            con = sqlite3.connect(db)
            try:
                pred_rows = execute(con, psql) if psql else []
            finally:
                con.close()
            if schema_from_sql(sql).get("is_aggregation"):
                g = gold_table_from_sql(gold_rows, sql)
                p = predicted_table_from_rows(pred_rows, gold=g)
                m = json_ready_metrics(evaluate_aggregation_tables(p, g, config=config))
                s = float(m["rank"]["structure_fbeta_score"])
                for k, v in m["rank"]["cell_f1"].items():
                    for t in TAUS:
                        if abs(float(k) - t) < 1e-9:
                            res[t] = round(s * float(v), 4)
        except Exception as exc:  # noqa: BLE001 - a query that fails to run scores 0, as in the recorded scores
            res = {t: 0.0 for t in TAUS} | {"error": str(exc)[:200]}
        out[qid] = res
    gold_conn.close()
    return out


def served_view(corpus: str, run: str, out: Path) -> Path:
    """The run's final table as it served queries: exp_cause.final_view (every cell the run read, the stronger
    reader's replacements applied) plus the list-item filter on the columns the run's plan switched it on for, with
    the rule the recorded runs used (a cell with no stated item is emptied: QUWARTS_ITEMFILTER_EMPTY=1)."""
    import shutil

    from quwarts.core.adapt import catalogue as K
    from quwarts.core.represent import Config, build
    from quwarts.core.router.comparator import is_null
    from quwarts.core.router.context_probe import FieldSpec
    from quwarts.core.router.corpus_features import read_document
    from quwarts.eval.exp_cause import fields_of, write_column

    assert not K.FILTER_KEEP, "set QUWARTS_ITEMFILTER_EMPTY=1: the recorded runs emptied cells with no stated item"
    view = out / "served.view.db"
    if view.exists():
        return view
    R = D.R
    ctx = R.context(corpus)
    src = final_view(corpus, run, 100, out).with_name("all.db")
    st = json.loads((EXP / run / "live" / corpus / "state" / "fixed4-attribute_pool_100.json").read_text())
    fields = fields_of(corpus)
    for t, plan in st.get("frozen", {}).items():
        fields = {**fields, **{k: FieldSpec(**{**v, "choices": tuple(v["choices"])}) for k, v in plan["fields"].items()}}
    db = out / "served.db"
    shutil.copy2(src, db)
    con = sqlite3.connect(src)
    for t, plan in st.get("frozen", {}).items():
        for col, stat in plan.get("stats", {}).items():
            a = col.split(".", 1)[1]
            if stat.get("kind") != "list" or not stat.get("item_filter"):
                continue
            new = {}
            for d, v in con.execute(f'SELECT doc_id, "{a}" FROM "{t}"').fetchall():
                if is_null(v) or d not in ctx.docs[t]:
                    continue
                nv = K.filter_list_items(v, read_document(Path(ctx.docs[t][d])).lower())
                if K.norm(nv) != K.norm(v):
                    new[d] = nv
            if new:
                write_column(db, t, a, new)
    con.close()
    build(db, view, ctx.spec, fields, dict(ctx.catalog), Config(t0=True))
    return view


def main(argv=None) -> int:
    args = argv or sys.argv[1:]
    sp = Path(args[0])
    corpora = args[1:] or ["cspaper", "player", "art", "med", "legal"]
    dest = EXP / "WHY" / "tau"
    dest.mkdir(parents=True, exist_ok=True)
    for c in corpora:
        design = json.loads((EXP.parent / "drift_live_ollama" / c / "fixed4_attribute_pool_design.json").read_text())
        tests = list(dict.fromkeys(design["test"]))
        per_doc = json.loads((DOCETL / c / "per_query.json").read_text())
        doc_items = [(q, DOCETL / c / "db" / f"{safe(q)}.db") for q in tests if q in per_doc and (DOCETL / c / "db" / f"{safe(q)}.db").exists()]
        common = [q for q, _ in doc_items]
        res = {"corpus": c, "test_queries": len(tests), "docetl_answered": len(common), "systems": {}}
        d = score_multi(c, doc_items)
        res["systems"]["DocETL"] = {"runs": [{"recorded_20": round(S.mean(per_doc[q]["benchmark"] for q in common), 4),
                                              **{f"{t:.0%}": round(S.mean(d[q][t] for q in common), 4) for t in TAUS}}]}
        for name, runs in OURS.items():
            rows = []
            for run in runs:
                stream = EXP / run / "live" / c / "streams" / "fixed4-attribute_pool_100.jsonl"
                if not stream.exists():
                    continue
                rec = {json.loads(x)["qid"]: json.loads(x).get("benchmark") or 0.0 for x in stream.read_text().splitlines() if x.strip()}
                view = served_view(c, run, sp / "fv" / f"{c}_{run}")
                o = score_multi(c, [(q, view) for q in tests])
                rows.append({"run": run, "recorded_20_all": round(S.mean(rec.get(q, 0.0) for q in tests), 4),
                             "recorded_20": round(S.mean(rec.get(q, 0.0) for q in common), 4),
                             **{f"{t:.0%}": round(S.mean(o[q][t] for q in common), 4) for t in TAUS}})
            if rows:
                res["systems"][name] = {"runs": rows}
        (dest / f"{c}.json").write_text(json.dumps(res, indent=1))
        print(c, json.dumps(res["systems"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

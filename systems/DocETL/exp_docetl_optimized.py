"""DocETL with its own optimizer, per query and table, then the optimized plan on every document.

Each (query, table) starts from the same map DocETL runs in run_docetl_drift (same prompt, same output schema, the
DOCETL_STR_COERCE fix), and is optimized with:
  moar  DocETL's current optimizer (MOARSearch): rewrites searched against an evaluation function. The function is
        field accuracy against the correct data on a labeled sample of documents (default 30), so this arm uses
        labels our system never sees (an upper bound for DocETL). The plan with the best sample accuracy is kept.
  v1    DocETL's earlier optimizer (Pipeline.optimize): LLM agents propose rewrites and LLM validators judge them on
        samples; no labels.
The agents run on --agent-model (Claude Haiku); the pipeline's own steps may use only --model (the executing model).
The chosen plan runs on all documents; tables are built and scored as in run_docetl_drift (answer keys included).
Output: results/docetl_optimized/<optimizer>-<model tag>/<corpus>/...

    OLLAMA_HOST=... ANTHROPIC_API_KEY=... PYTHONPATH=systems/WDIRS QUWARTS_LLM=ollama QUWARTS_DRIFT_DESIGN=drift_paired \
        ~/venvs/quwarts/bin/python systems/DocETL/exp_docetl_optimized.py --optimizer moar --corpus player --qids 'real:player#QJ14'
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--optimizer", required=True, choices=["moar", "v1"])
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--qids", nargs="+", required=True)
    ap.add_argument("--model", help="executing model (litellm id); default: the local Ollama model")
    ap.add_argument("--agent-model", default="anthropic/claude-haiku-5-5")
    ap.add_argument("--sample", type=int, default=30, help="labeled documents for MOAR's evaluation function")
    ap.add_argument("--iterations", type=int, default=10, help="MOAR search iterations per (query, table)")
    ap.add_argument("--threads", type=int, default=8)
    a = ap.parse_args(argv)
    os.environ["DOCETL_STR_COERCE"] = "1"

    import run_docetl_drift as RD
    import yaml
    from quwarts.core.router.comparator import is_null
    from quwarts.eval import drift_live as D
    from quwarts.eval.exp_analysis import gold_by_doc
    from quwarts.eval.exp_docetl_variation import catalogs
    from quwarts.eval.exp_open import correct
    from quwarts.eval.exp_tau import TAUS, score_multi

    if a.model:
        RD.MODEL, RD.API_BASE = a.model, None
    else:
        os.environ["OLLAMA_API_BASE"] = RD.API_BASE  # steps the optimizer creates reach the same server
    import litellm

    # Only the executing model exists here: a step the agents write with a model name copied from DocETL's directive
    # templates (gpt-4o, gpt-4o-mini, ...) runs on the executing model instead of failing for lack of an OpenAI key.
    litellm.model_alias_map = {m: RD.MODEL for m in ("gpt-4o", "gpt-4o-mini", "gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5.1",
                                                     "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "azure/gpt-4o-mini", "gpt-3.5-turbo")}
    kwargs = {"max_tokens": RD.ANSWER_ROOM} | ({"num_ctx": RD.NUM_CTX, "api_base": RD.API_BASE} if RD.API_BASE else {})
    c = a.corpus
    ctx = D.R.context(c)
    cat = catalogs(c)
    if any(q.startswith("conflict:") for q in a.qids):
        from quwarts.eval.validate_conflicts import load as load_conflicts

        cat.update(load_conflicts(c))
    for q in a.qids:
        ctx.catalog.setdefault(q, cat[q])
    RD.track_tokens()
    tag = (a.model or "ollama_chat/qwen").split("/")[-1].split(":")[0]
    root = RD.ROOT / "results" / "docetl_optimized" / f"{a.optimizer}-{tag}" / c
    root.mkdir(parents=True, exist_ok=True)
    per_path = root / "per_query.json"
    per = json.loads(per_path.read_text()) if per_path.exists() else {}
    gdoc = gold_by_doc(c)

    def base_config(name, table, attrs, fields, sql, data_path, out_path):
        numeric = {x for x in attrs if getattr(fields.get(f"{table}.{x}"), "value_type", "str") in ("int", "float")}
        descriptions = {x: getattr(fields.get(f"{table}.{x}"), "description", None) for x in attrs}
        template = RD.prompt_template(table, attrs, numeric, sql, descriptions)
        return {
            "default_model": RD.MODEL,
            "datasets": {"docs": {"type": "file", "path": str(data_path)}},
            "operations": [{"name": "extract_fields", "type": "map", "prompt": template, "model": RD.MODEL,
                            "output": {"schema": {x: ("number" if x in numeric else "str") for x in attrs}},
                            "skip_on_error": True, "litellm_completion_kwargs": kwargs,
                            "optimize": True}],  # the v1 optimizer only rewrites operations marked optimize: true
            "pipeline": {"steps": [{"name": "extract_step", "input": "docs", "operations": ["extract_fields"]}],
                         "output": {"type": "file", "path": str(out_path), "intermediate_dir": str(out_path.parent / "intermediate")}},
        }, numeric, template

    def run_config(cfg, workdir):
        from docetl.runner import DSLRunner

        cwd = os.getcwd()
        try:
            os.chdir(workdir)
            runner = DSLRunner(cfg, max_threads=a.threads)
            runner.load_run_save()
        finally:
            os.chdir(cwd)
        p = Path(cfg["pipeline"]["output"]["path"])
        return json.loads(p.read_text()) if p.exists() else []

    for qid in a.qids:
        if qid in per:
            continue
        sql = cat[qid]
        fields, reads = D.C.design(ctx.spec, {qid: sql})
        qdir = root / RD.safe(qid)
        tables, numeric_by_t, info = {}, {}, []
        for r in reads:
            if r.table not in ctx.names or not r.attributes:
                continue
            t, attrs = r.table, list(r.attributes)
            tdir = qdir / f"table_{t}"
            tdir.mkdir(parents=True, exist_ok=True)
            texts = {d: Path(p).read_text(errors="ignore") for d, p in ctx.docs[t].items()}
            probe_cfg, numeric, template = base_config("probe", t, attrs, fields, sql, tdir / "x.json", tdir / "y.json")
            full = [{"doc_id": d, "text": RD.fit(texts[d], template)} for d in ctx.names[t]]
            (tdir / "all_docs.json").write_text(json.dumps(full))
            before, started = dict(RD.TOKENS), time.time()
            if a.optimizer == "moar":
                gt = {str(d).rsplit(".", 1)[0]: row for d, row in gdoc.get(t, {}).items()}
                labeled = [x for x in full if any(not is_null((gt.get(str(x["doc_id"]).rsplit(".", 1)[0]) or {}).get(f)) for f in attrs)]
                sample = random.Random(f"{qid}|{t}").sample(labeled, min(a.sample, len(labeled)))
                (tdir / "sample_docs.json").write_text(json.dumps(sample))
                (tdir / "sample_gold.json").write_text(json.dumps({x["doc_id"]: {f: (gt.get(str(x["doc_id"]).rsplit(".", 1)[0]) or {}).get(f) for f in attrs} for x in sample}, default=str))
                (tdir / "evaluate.py").write_text(EVAL_TEMPLATE.format(gold=str(tdir / "sample_gold.json"), fields=json.dumps(attrs)))
                cfg, _, _ = base_config("moar", t, attrs, fields, sql, tdir / "sample_docs.json", tdir / "moar_root_output.json")
                cfg["optimizer_config"] = {"type": "moar", "save_dir": str(tdir / "moar"), "available_models": [RD.MODEL],
                                           "evaluation_file": str(tdir / "evaluate.py"), "metric_key": "field_accuracy",
                                           "max_iterations": a.iterations, "rewrite_agent_model": a.agent_model}
                ypath = tdir / "pipeline.yaml"
                ypath.write_text(yaml.safe_dump(cfg, sort_keys=False))
                from docetl.moar.cli_helpers import run_moar_optimization

                cwd = os.getcwd()
                try:
                    os.chdir(tdir)
                    summary = run_moar_optimization(yaml_path=str(ypath), optimizer_config=cfg["optimizer_config"])
                finally:
                    os.chdir(cwd)
                (tdir / "moar_summary.json").write_text(json.dumps(summary, indent=1, default=str))
                best_yaml = pick_best_moar(tdir / "moar", summary)
                plan = yaml.safe_load(Path(best_yaml).read_text()) if best_yaml else cfg
            else:
                from docetl.runner import DSLRunner

                sample = random.Random(f"v1|{qid}|{t}").sample(full, min(a.sample, len(full)))  # unlabeled: no gold used
                (tdir / "v1_sample_docs.json").write_text(json.dumps(sample))
                cfg, _, _ = base_config("v1", t, attrs, fields, sql, tdir / "v1_sample_docs.json", tdir / "v1_unused.json")
                cfg["optimizer_config"] = {"rewrite_agent_model": a.agent_model, "judge_agent_model": a.agent_model}
                cwd = os.getcwd()
                try:
                    os.chdir(tdir)
                    runner = DSLRunner(cfg, base_name=str(tdir / "v1"), yaml_file_suffix="v1", max_threads=a.threads)
                    plan, opt_cost = runner.optimize(return_pipeline=False)
                finally:
                    os.chdir(cwd)
                best_yaml = None
                (tdir / "v1_plan.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
            opt_tokens = {k: RD.TOKENS[k] - before[k] for k in RD.TOKENS}
            # the chosen plan on every document
            plan = dict(plan)
            plan.pop("optimizer_config", None)
            for ds in plan.get("datasets", {}).values():
                ds["path"] = str(tdir / "all_docs.json")
            plan.setdefault("pipeline", {})["output"] = {"type": "file", "path": str(tdir / "pipeline_output.json"), "intermediate_dir": str(tdir / "final_intermediate")}
            (tdir / "plan_used.yaml").write_text(yaml.safe_dump(plan, sort_keys=False))
            before2 = dict(RD.TOKENS)
            rows = RD.clean(run_config(plan, tdir), attrs)
            got = {}
            for row in rows:  # a plan may emit one row per chunk: keep one row per document, first non-empty value per field
                d = row.get("doc_id")
                cur = got.setdefault(d, {"doc_id": d})
                for x in attrs:
                    if cur.get(x.lower()) in (None, "", -1) and row.get(x.lower()) not in (None, "", -1):
                        cur[x.lower()] = row.get(x.lower())
            tables[t] = list(got.values())
            numeric_by_t[t] = {x.lower() for x in numeric}
            run_tokens = {k: RD.TOKENS[k] - before2[k] for k in RD.TOKENS}
            info.append({"table": t, "fields": attrs, "plan_ops": [o.get("type") + ":" + o.get("name", "") for o in plan.get("operations", [])],
                         "best_plan": str(best_yaml) if best_yaml else None, "optimization_tokens": opt_tokens, "run_tokens": run_tokens,
                         "rows": len(tables[t]), "documents": len(full), "seconds": round(time.time() - started, 1)})
        db = RD.build_db(c, sql, tables, numeric_by_t, root / "db" / f"{RD.safe(qid)}.db")
        sc = score_multi(c, [(qid, db)])[qid]
        per[qid] = {"score": {f"{t_:.0%}": sc.get(t_) for t_ in TAUS}, "tables": info}
        import fcntl  # several processes write the same collection's file: merge under a lock

        with open(str(per_path) + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            disk = json.loads(per_path.read_text()) if per_path.exists() else {}
            disk[qid] = per[qid]
            per_path.write_text(json.dumps(disk, indent=1, default=str))
        tok = sum(sum(i["optimization_tokens"].get(k, 0) + i["run_tokens"].get(k, 0) for k in ("prompt", "completion")) for i in info)
        print(f"{a.optimizer}-{tag} {c:8s} {qid:32s} score@20 {per[qid]['score']['20%']:.3f} @0 {per[qid]['score']['0%']:.3f}  "
              f"plans {[i['plan_ops'] for i in info]}  {tok / 1e6:.2f}M tok (executing model)", flush=True)
    return 0


def pick_best_moar(save_dir: Path, summary: dict):
    """The plan MOAR evaluated with the highest field accuracy on the labeled sample (ties: lower cost), read from
    its Pareto frontier and evaluation file. No fallback: if MOAR evaluated nothing, the original plan is used."""
    cands = []
    pf = save_dir / "pareto_frontier.json"
    if pf.exists():
        for r in json.loads(pf.read_text()):
            if isinstance(r.get("accuracy"), (int, float)) and r.get("yaml_path") and Path(r["yaml_path"]).exists():
                cands.append((r["accuracy"], -float(r.get("cost") or 0), r["yaml_path"]))
    ev = save_dir / "evaluation_metrics.json"
    if ev.exists():
        for r in json.loads(ev.read_text()):
            y = save_dir / str(r.get("file", "")).replace(".json", ".yaml")
            if isinstance(r.get("field_accuracy"), (int, float)) and y.exists():
                cands.append((r["field_accuracy"], -float(r.get("cost") or 0), str(y)))
    return max(cands)[2] if cands else None


EVAL_TEMPLATE = '''import json
from docetl.utils_evaluation import register_eval
from quwarts.core.router.comparator import is_null
from quwarts.eval.exp_open import correct

GOLD = {gold!r}
FIELDS = {fields}


@register_eval
def evaluate(dataset_file_path, results_file_path):
    gold = json.load(open(GOLD))
    rows = json.load(open(results_file_path))
    got = {{}}
    for r in rows:
        d = r.get("doc_id")
        cur = got.setdefault(d, {{}})
        for f in FIELDS:
            v = r.get(f, r.get(f.lower()))
            if cur.get(f) in (None, "", -1) and v not in (None, "", -1, "Not found"):
                cur[f] = v
    n = right = 0
    for d, g in gold.items():
        for f in FIELDS:
            if is_null(g.get(f)):
                continue
            n += 1
            v = got.get(d, {{}}).get(f)
            right += bool(v not in (None, "", -1) and correct(v, g[f], 0.0))
    return {{"field_accuracy": right / n if n else 0.0, "labeled_answers": n}}
'''


if __name__ == "__main__":
    raise SystemExit(main())

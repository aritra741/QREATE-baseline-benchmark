"""The planner on Bench-U's own workload and metric (BENCHU_OPPORTUNITIES.md, opening A).

    python -m quwarts.eval.exp_benchu --run V3 --datasets Player,CSPaper,Art,Med,Legal [--judge local|none]

For each dataset: Bench-U's SQL files are split into per-query folders with its preprocessor; the run's final served
table (``exp_cause.final_view``) gets the ground truth's id columns (the document's number, or the paper's file
stem); every query is executed on it with the id columns Bench-U injects for alignment; ``evaluation.run_eval``
scores each result against the ground truth with exact matching plus the LLM judge (the local 7B through the
OpenAI-compatible endpoint, as ``evaluation/conf/api_key.yaml`` says); the per-query macro F1 is averaged by task.
The amortized cost (tokens per document per query) comes from the run's stream and build.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import statistics as S
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from sqlglot import exp, parse_one

from quwarts.eval.exp_analysis import EXP, REPO
from quwarts.eval.exp_cause import final_view

SCRATCH = Path("/scratch/general/vast/u1592362/quwarts_exp/benchu")
CORPUS = {"CSPaper": "cspaper", "Player": "player", "Art": "art", "Med": "med", "Legal": "legal"}
ALIASES = {"Legal": {"legal_case": "legal"}}  # table names Bench-U's SQL uses that the ground truth files do not
PY = str(Path.home() / "venvs" / "quwarts" / "bin" / "python")


def prepare_gt(ds: str) -> Path:
    """A copy of the ground-truth tables with an ``id`` column everywhere (papers: the file stem) and the aliases."""
    out = SCRATCH / "gt" / ds
    if out.exists():
        return out
    out.mkdir(parents=True)
    for csv in (REPO / "Query" / ds).glob("*.csv"):
        df = pd.read_csv(csv)
        if not any(c.lower() == "id" for c in df.columns):
            if "pdf_filename" in df.columns:
                df["id"] = df["pdf_filename"].astype(str).str.replace(r"\.pdf$", "", regex=True)
            else:
                df["id"] = range(1, len(df) + 1)
        df.to_csv(out / csv.name, index=False)
        for alias, real in ALIASES.get(ds, {}).items():
            if csv.stem.lower() == real:
                df.to_csv(out / f"{alias}.csv", index=False)
    return out


def preprocess(ds: str, root: Path) -> list[Path]:
    """Bench-U's per-query folders (sql.json) for every SQL file of the dataset."""
    folders = []
    for task in ("Select", "Filter", "Join", "Agg", "Mixed"):
        for f in sorted((REPO / "Query" / ds / task).glob("*.sql")):
            subprocess.run([PY, "-m", "evaluation.sql_preprocessor", "--dataset", ds, "--task", task, "--sql-file", str(f),
                            "--attributes-file", str(REPO / "Query" / ds / f"{ds}_attributes.json"), "--output-root", str(root)],
                           cwd=REPO, check=True, capture_output=True)
            folders += sorted((root / ds / task / f.stem).glob("*/"), key=lambda p: int(p.name))
    return folders


def with_ids(view: Path, ds: str) -> Path:
    """The run's view with Bench-U's id columns: the document's number, or the paper's file stem."""
    dest = view.with_name("benchu.view.db")
    if dest.exists():
        return dest
    shutil.copy2(view, dest)
    con = sqlite3.connect(dest)
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
        if "doc_id" not in cols or "id" in cols:
            continue
        if ds == "CSPaper":
            con.execute(f'ALTER TABLE "{t}" ADD COLUMN id TEXT')
            con.execute(f'UPDATE "{t}" SET id = replace(replace(doc_id, ".txt", ""), ".pdf", "")')
        else:
            con.execute(f'ALTER TABLE "{t}" ADD COLUMN id INTEGER')
            con.execute(f'UPDATE "{t}" SET id = CAST(replace(doc_id, ".txt", "") AS INTEGER)')
    for alias, real in ALIASES.get(ds, {}).items():
        con.execute(f'CREATE VIEW IF NOT EXISTS "{alias}" AS SELECT * FROM "{real}"')
    con.commit()
    con.close()
    return dest


def injected_sql(sql: str) -> tuple[str, str]:
    """Bench-U's alignment columns added to the select list: ``id`` for a single-table query, ``{table}.id`` for a
    join, nothing for an aggregation. Returns (sql, query type)."""
    sys.path.insert(0, str(REPO))
    from evaluation.tools.sql_parser import SqlParser

    parsed = SqlParser().parse(sql)
    e = parse_one(sql.rstrip(";"), read="sqlite")
    if parsed.query_type == "aggregation":
        return e.sql(dialect="sqlite"), "aggregation"
    existing = {(i.output_name or "").lower() for i in parsed.select_items} | {(i.source_name or "").lower() for i in parsed.select_items}
    if parsed.query_type == "join":
        for t in parsed.tables:
            if f"{t}.id".lower() not in existing:
                e = e.select(exp.alias_(exp.column("id", table=t), f"{t}.id", quoted=True))
    elif "id" not in existing:
        e = e.select(exp.alias_(exp.column("id"), "id"))
    return e.sql(dialect="sqlite"), parsed.query_type


def run_query(view: Path, folder: Path) -> dict:
    sql = json.loads((folder / "sql.json").read_text())["sql"]
    try:
        sql2, qtype = injected_sql(sql)
        con = sqlite3.connect(view)
        df = pd.read_sql_query(sql2, con)
        con.close()
        df.to_csv(folder / "result.csv", index=False)
        return {"rows": len(df), "type": qtype}
    except Exception as e:  # a query the view cannot answer (a table never read): an empty result
        pd.DataFrame().to_csv(folder / "result.csv", index=False)
        return {"rows": 0, "type": "error", "error": str(e)[:160]}


def evaluate(ds: str, folder: Path, gt: Path, judge: str) -> dict | None:
    cmd = [PY, "-m", "evaluation.run_eval", "--dataset", ds, "--task", folder.parent.parent.name, "--sql-file", str(folder / "sql.json"),
           "--result-csv", str(folder / "result.csv"), "--attributes-file", str(REPO / "Query" / ds / f"{ds}_attributes.json"),
           "--gt-dir", str(gt), "--output-dir", str(folder), "--log-level", "WARNING"]
    cmd += ["--llm-provider", "openai", "--llm-model", "openai/qwen2.5:7b-instruct"] if judge == "local" else ["--llm-provider", "none"]
    env = dict(os.environ)
    if judge == "local":
        srv = json.loads((EXP / "servers" / "main.json").read_text())
        env.update({"OPENAI_API_KEY": "ollama", "OPENAI_API_BASE": f"http://{srv['host']}/v1"})
    r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=1800)
    acc = folder / "acc.json"
    if not acc.exists():
        return {"error": (r.stderr or r.stdout)[-300:]}
    return json.loads(acc.read_text())


def cost(corpus: str, run: str, key: str = "fixed4-attribute_pool/100") -> dict:
    """Tokens per document per query over the run's test workload, build included (Bench-U's unit is thousand
    tokens per document per query, per query run alone)."""
    live = EXP / run / "live" / corpus if run != "recorded" else REPO / "results" / "drift_live_ollama" / corpus
    stream = live / "streams" / f"{key.replace('/', '_')}.jsonl"
    rs = [json.loads(l) for l in stream.read_text().splitlines() if l.strip()] if stream.exists() else []
    patch = sum(r["input_tokens"] + r["output_tokens"] for r in rs)
    repair = sum(v.get("tokens", 0) or 0 for r in rs for p in r.get("planner", {}).values() for v in (p.get("repair") or {}).values())
    bf = live / "builds" / "fixed4_attribute_pool_100.json"
    build = json.loads(bf.read_text()).get("measured_tokens", 0) if bf.exists() else 0
    from quwarts.eval import drift_run as R

    docs = sum(len(v) for v in R.context(corpus).names.values())
    return {"queries": len(rs), "documents": docs, "patch_tokens": patch, "repair_tokens": repair, "build_tokens": build,
            "k_tokens_per_doc_per_query": round((patch + repair + build) / 1000 / max(1, docs) / max(1, len(rs)), 3)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default="V3")
    ap.add_argument("--level", type=int, default=100)
    ap.add_argument("--datasets", default="Player,CSPaper,Art,Med,Legal")
    ap.add_argument("--judge", default="local", choices=["local", "none"])
    ap.add_argument("--limit", type=int, help="queries per dataset (smoke test)")
    ap.add_argument("--key", help="the run's stream key, e.g. fixed4-benchu/100 (default: the drift level's stream)")
    a = ap.parse_args(argv)
    out = {"run": a.run, "judge": a.judge, "datasets": {}}
    for ds in a.datasets.split(","):
        corpus = CORPUS[ds]
        root = SCRATCH / a.run / a.judge
        gt = prepare_gt(ds)
        folders = preprocess(ds, root)
        if a.limit:
            folders = folders[: a.limit]
        view = with_ids(final_view(corpus, a.run, a.level, SCRATCH / "views" / a.run / corpus, a.key), ds)
        by_task = defaultdict(list)
        errors = 0
        rows = []
        for folder in folders:
            task = folder.parent.parent.name
            rq = run_query(view, folder)
            acc = evaluate(ds, folder, gt, a.judge)
            f1 = acc.get("macro_f1") if acc and "macro_f1" in acc else None
            if f1 is None:
                errors += 1
            else:
                by_task[task].append(f1)
            rows.append({"task": task, "query": f"{folder.parent.name}/{folder.name}", "rows": rq["rows"], "type": rq["type"], "f1": f1,
                         "precision": acc.get("macro_precision") if acc else None, "recall": acc.get("macro_recall") if acc else None,
                         "error": rq.get("error") or (acc.get("error") if acc else "no acc")})
            print(f"  {ds} {task} {folder.parent.name}/{folder.name}: rows={rq['rows']} f1={f1}", flush=True)
        summary = {t: {"queries": len(v), "mean_f1": round(S.mean(v), 3)} for t, v in by_task.items()}
        allf = [x for v in by_task.values() for x in v]
        out["datasets"][ds] = {"by_task": summary, "mean_f1": round(S.mean(allf), 3) if allf else None, "queries": len(folders),
                              "unscored": errors, "cost": cost(corpus, a.run, a.key or "fixed4-attribute_pool/100"), "queries_detail": rows}
        print(f"{ds}: mean F1 {out['datasets'][ds]['mean_f1']} over {len(allf)} queries ({errors} unscored); {summary}; cost {out['datasets'][ds]['cost']['k_tokens_per_doc_per_query']}k tokens/doc/query", flush=True)
    dest = EXP / "BENCHU" / f"{a.run}_{a.judge}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

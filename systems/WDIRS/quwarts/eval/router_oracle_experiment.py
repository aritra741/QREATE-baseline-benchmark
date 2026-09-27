"""Proxy + oracle-sample experiment (Legal, constant-independent system). Grading with gold is AUDIT only.

Proxy: the constant-independent system's table (legal_agnostic, blank base). Oracle: a careful read
with the same model (Qwen 2.5 7B), same generated meanings, on a uniform random sample of documents,
for the columns in ORACLE_COLUMNS:
  - count columns (numeric in the SQL and the generated meaning says "number of" / "count of"):
    the item is defined once from BM25-retrieved passages of 20 other documents; then every
    2,000-token chunk of the whole document is asked for the items verbatim; items that occur in
    the chunk are kept, unioned over chunks, deduped and counted;
  - other columns: one focused call per column on the document (first 20,000 tokens) with the same
    field line the proxy saw, asking for the value and a verbatim supporting quote.
A second, independent read (temperature 0.7) on the first REPEAT_DOCS sampled documents measures the
oracle's self-agreement (gold-free). Estimation: ``core.router.estimate`` (difference estimator, 95% CI).

Pre-registered questions: (1) per document against gold, is the oracle more accurate than the proxy
on these columns? (2) on the queries that use them, does the corrected estimate beat the proxy-only
answer (benchmark product), and do the intervals cover gold?

    python -m quwarts.eval.router_oracle_experiment --stage define|oracle|report
"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from quwarts.core.ledger import TokenLedger
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router.context_probe import truncate
from quwarts.core.router.corpus_features import list_documents, read_document
from quwarts.core.router.estimate import estimate, plan_query, project
from quwarts.core.router.executor import commit_value
from quwarts.core.router.registry import PROJECT, RESULTS, get_corpus
from quwarts.eval import router_shared_read_run as rs
from quwarts.eval.router_count_probe import normalize_item, parse_items
from quwarts.eval.router_count_probe2 import (bm25_ranked, chunk_prompt, chunks, define_prompt, definition_text,
                                              parse_json, squash)

CORPUS = "legal"
ORACLE_COLUMNS = ["case_number", "legal_basis_num", "first_judge", "defendant_current_status"]
N_SAMPLE = 100
N_DEFINE = 20
REPEAT_DOCS = 30
SEED = 20260928
FOCUS_WINDOW = 20_000
SYSTEM = "You read documents carefully and answer in JSON only."
_COUNT_MEANING = re.compile(r"\b(?:number|count) of\b", re.I)


def focus_prompt(field_line: str, text: str) -> str:
    return ("Read the document and determine one database field.\n"
            f"{field_line}\n"
            "Answer for this document only. Quote the sentence that supports your answer, copied exactly "
            "from the document.\n"
            'Return JSON only: {"value": <the value, or null if the document does not say>, "evidence": "<quote>"}\n\n'
            f"Document:\n{text}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["define", "oracle", "report"], required=True)
    parser.add_argument("--workers", type=int, default=48)
    parser.add_argument("--deadline", type=float, default=140.0)
    args = parser.parse_args(argv)
    rs.TAG = "agnostic"
    spec, train, test, fields, _reads = rs.setup(CORPUS, "per_attribute")
    table = spec.tables[0].sql_name
    root = RESULTS / "quwarts_router_v3" / f"{spec.name}_agnostic"
    descs = json.loads((root / "shared_read_per_attribute" / "descriptions_per_attribute.json").read_text())
    proxy_db = root / "shared_read_per_attribute" / "read_first_blank.db"
    out = root / "oracle_experiment"
    out.mkdir(parents=True, exist_ok=True)
    cache_path = out / "calls.jsonl"
    cache: dict[tuple, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            r = json.loads(line)
            cache[tuple(r["key"])] = r

    paths = list_documents(spec.table(table))
    sample = sorted(random.Random(SEED).sample(paths, N_SAMPLE), key=lambda p: p.name)
    in_sample = set(sample)
    define_docs = sorted(random.Random(SEED + 1).sample([p for p in paths if p not in in_sample], N_DEFINE),
                         key=lambda p: p.name)
    repeat = sample[:REPEAT_DOCS]
    q = lambda col: f"{table}.{col}"  # noqa: E731
    meaning = {c: (descs.get(q(c), {}).get("meaning") or c.replace("_", " ")) for c in ORACLE_COLUMNS}
    count_cols = [c for c in ORACLE_COLUMNS
                  if fields[q(c)].value_type in ("int", "float") and _COUNT_MEANING.search(meaning[c])]
    focus_cols = [c for c in ORACLE_COLUMNS if c not in count_cols]
    text = {p.name: read_document(p) for p in sample + define_docs}
    doc_chunks = {name: chunks(t) for name, t in text.items()}
    define_chunks = {p.stem: doc_chunks[p.name] for p in define_docs}  # bm25_ranked keys chunks by file stem
    (out / "design.json").write_text(json.dumps({
        "sample": [p.name for p in sample], "define_docs": [p.name for p in define_docs],
        "repeat_docs": [p.name for p in repeat], "count_columns": count_cols, "focus_columns": focus_cols,
        "meanings": meaning, "proxy_db": str(proxy_db.relative_to(RESULTS))}, indent=2))

    lock, t0, callers = threading.Lock(), time.time(), {}

    def caller(kind: str):
        if not callers:
            from quwarts.core.llm.openrouter import load_env_file, make_caller
            load_env_file(PROJECT / ".env")
            ledger = TokenLedger(theta=10**12)
            callers["define"] = make_caller(ledger, max_tokens=700)
            callers["list"] = make_caller(ledger, max_tokens=1200)
            callers["list_rep"] = make_caller(ledger, temperature=0.7, max_tokens=1200)
            callers["focus"] = make_caller(ledger, max_tokens=300)
            callers["focus_rep"] = make_caller(ledger, temperature=0.7, max_tokens=300)
        return callers[kind]

    def call(key: tuple, kind: str, prompt: str) -> bool:
        if key in cache:
            return True
        if time.time() - t0 > args.deadline:
            return False
        response = caller(kind).complete(prompt, "oracle_experiment", system=SYSTEM, key="/".join(map(str, key)))
        rec = {"key": list(key), "response": response,
               "tokens": count_tokens(SYSTEM) + count_tokens(prompt) + count_tokens(response)}
        with lock:
            cache[key] = rec
            with cache_path.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
        return True

    def definition(col: str) -> str:
        d = parse_json(cache[("define", col)]["response"]) or {}
        passages = squash(" ".join(bm25_ranked(meaning[col], define_docs, define_chunks)[:3]))
        d["examples"] = [e for e in d.get("examples") or [] if isinstance(e, str) and squash(e) in passages]
        return definition_text(d)

    if args.stage == "define":
        for col in count_cols:
            call(("define", col), "define", define_prompt(col, meaning[col], bm25_ranked(meaning[col], define_docs, define_chunks)[:3]))
            print(col, "\n ", definition(col).replace("\n", "\n  "))
        return 0

    if args.stage == "oracle":
        tasks = []
        for col in count_cols:
            dtext = definition(col)
            for rep, docs in ((0, sample), (1, repeat)):
                for p in docs:
                    for i, ch in enumerate(doc_chunks[p.name]):
                        tasks.append((("chunk", col, p.name, i, rep), "list" if rep == 0 else "list_rep",
                                      chunk_prompt(col, meaning[col], dtext, ch)))
        for col in focus_cols:
            line = fields[q(col)].line()
            for rep, docs in ((0, sample), (1, repeat)):
                for p in docs:
                    tasks.append((("focus", col, p.name, rep), "focus" if rep == 0 else "focus_rep",
                                  focus_prompt(line, truncate(text[p.name], FOCUS_WINDOW))))
        with ThreadPoolExecutor(args.workers) as pool:
            done = sum(pool.map(lambda t: call(*t), tasks))
        print(json.dumps({"tasks": len(tasks), "done": done, "remaining": len(tasks) - done,
                          "tokens_so_far": sum(r["tokens"] for r in cache.values())}))
        return 0

    # ---------------- values (gold-free) ----------------
    def oracle_value(col: str, doc: str, rep: int) -> tuple[Any, dict]:
        if col in count_cols:
            items: set[str] = set()
            for i, ch in enumerate(doc_chunks[doc]):
                listed = parse_items(cache[("chunk", col, doc, i, rep)]["response"]) or []
                hay = squash(ch)
                items |= {normalize_item(x) for x in listed if squash(x) and squash(x) in hay and normalize_item(x)}
            return commit_value(len(items), fields[q(col)]), {"items": len(items)}
        parsed = parse_json(cache[("focus", col, doc, rep)]["response"]) or {}
        evidence = str(parsed.get("evidence") or "")
        return commit_value(parsed.get("value"), fields[q(col)]), {
            "evidence_verbatim": bool(squash(evidence)) and squash(evidence) in squash(text[doc])}

    oracle = {p.name: {} for p in sample}
    meta: dict[str, dict] = {}
    for col in ORACLE_COLUMNS:
        for p in sample:
            v, m = oracle_value(col, p.name, 0)
            oracle[p.name][col] = v
            meta.setdefault(col, {})[p.name] = m
    oracle_rep = {p.name: {col: oracle_value(col, p.name, 1)[0] for col in ORACLE_COLUMNS} for p in repeat}
    (out / "oracle_values.json").write_text(json.dumps({"oracle": oracle, "repeat": oracle_rep, "meta": meta}, indent=2))

    # oracle table: proxy rows of the sampled documents with the oracle columns replaced
    oracle_db = out / "oracle_rows.db"
    shutil.copyfile(proxy_db, oracle_db)
    conn = sqlite3.connect(oracle_db)
    for doc, vals in oracle.items():
        for col, v in vals.items():
            conn.execute(f'UPDATE "{table}" SET "{col}" = ? WHERE doc_id = ?', (v, doc))
    conn.commit()
    proxy_conn = sqlite3.connect(proxy_db)
    n_total = proxy_conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    # ---------------- estimates for every query (gold-free) ----------------
    all_q = {r["query_id"]: r["sql"] for r in train + test}
    uses = {qid: any(re.search(rf"\b{c}\b", s) for c in ORACLE_COLUMNS) for qid, s in all_q.items()}
    results_db = out / "answers.db"
    if results_db.exists():
        results_db.unlink()
    res = sqlite3.connect(results_db)
    answers: dict[str, dict] = {}

    def store(name: str, cols: list[str], rows: list[tuple]) -> None:
        res.execute(f'CREATE TABLE "{name}" ({", ".join(chr(34) + c + chr(34) for c in cols)})')
        res.executemany(f'INSERT INTO "{name}" VALUES ({", ".join("?" * len(cols))})', rows)

    for idx, (qid, sql) in enumerate(sorted(all_q.items())):
        cur = proxy_conn.execute(sql)
        pcols = [d[0] for d in cur.description]
        prows = cur.fetchall()
        store(f"proxy_{idx}", pcols, prows)
        plan = plan_query(sql)
        mode = "proxy"
        if uses[qid] and plan.supported:
            proxy = project(proxy_conn, plan)
            orows = {d: r for d, r in project(conn, plan).items() if d in oracle}
            for variant, sample_rows in (("corrected", orows), ("null_oracle", {d: proxy[d] for d in oracle})):
                est = estimate(plan, proxy, sample_rows, n_total)
                store(f"{variant}_{idx}", plan.order, [tuple(r[c] for c in plan.order) for r in est])
                if variant == "corrected":
                    answers[qid] = {"rows": est, "order": plan.order}
            mode = "corrected"
        else:
            store(f"corrected_{idx}", pcols, prows)
            store(f"null_oracle_{idx}", pcols, prows)
        answers.setdefault(qid, {})["mode"] = mode
        answers[qid]["idx"] = idx
        answers[qid]["reason"] = plan.reason
    res.commit()

    # ---------------- grading (AUDIT: gold is read only below) ----------------
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.core.router.comparator import value_score
    from quwarts.eval.router_execute_v3 import DATASET
    from quwarts.experiments.player_case80 import execute, score_split
    from quwarts.experiments.synthesize_case80 import gold_name
    from spp.config_grid import _build_in_memory_db

    gold_tables = load_ground_truth(gold_name(DATASET[spec.name]))
    gold_doc = {f"{str(r['id']).strip()}.txt": r for r in gold_tables[table]}
    types = spec.benchmark_attribute_descriptions(purpose="audit")["legal_case"]
    cur = proxy_conn.execute(f'SELECT * FROM "{table}"')
    names = [c[0] for c in cur.description]
    proxy_rows = {str(r[0]): dict(zip(names, r)) for r in cur.fetchall()}

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    audit = {}
    for col in ORACLE_COLUMNS:
        vt = str(types[col].get("value_type", "str"))
        docs = [p.name for p in sample]
        acc = lambda get: sum(value_score(get(d), gold_doc[d].get(col), vt) for d in docs) / len(docs)  # noqa: E731
        entry = {"type": vt, "proxy_acc": acc(lambda d: proxy_rows[d][col]), "oracle_acc": acc(lambda d: oracle[d][col]),
                 "oracle_self_agreement": sum(value_score(oracle[d][col], oracle_rep[d][col], vt) for d in oracle_rep) / len(oracle_rep),
                 "proxy_oracle_agreement": sum(value_score(oracle[d][col], proxy_rows[d][col], vt) for d in docs) / len(docs)}
        if col in count_cols:
            g = [num(gold_doc[d].get(col)) for d in docs]
            for who, get in (("proxy", lambda d: proxy_rows[d][col]), ("oracle", lambda d: oracle[d][col])):
                pv = [num(get(d)) for d in docs]
                ok = [(p, t) for p, t in zip(pv, g) if t is not None]
                entry[f"{who}_mean_ratio"] = (sum(p or 0 for p, _ in ok) / len(ok)) / (sum(t for _, t in ok) / len(ok))
                entry[f"{who}_within20"] = sum(p is not None and abs(p - t) <= 0.2 * max(t, 1) for p, t in ok) / len(ok)
        else:
            entry["evidence_verbatim_rate"] = sum(m.get("evidence_verbatim", False) for m in meta[col].values()) / len(docs)
        audit[col] = entry

    def product_scores(prefix: str) -> dict[str, float]:
        rows = [{"query_id": qid, "sql": sql, "pack": qid.split(":")[0],
                 "pred_sql": f'SELECT * FROM "{prefix}_{answers[qid]["idx"]}"', "pred_db": str(results_db)}
                for qid, sql in sorted(all_q.items())]
        rep = score_split(rows, results_db, gold_tables, dataset=gold_name(DATASET[spec.name]))
        return {p["query_id"]: float(p.get("structure_f2") or 0) * float(p.get("cell_f1_20") or 0) for p in rep["per_query"]}

    scores = {v: product_scores(v) for v in ("proxy", "null_oracle", "corrected")}
    gold_conn = _build_in_memory_db(gold_tables)
    coverage, widths = [], []
    for qid, a in answers.items():
        if a.get("mode") != "corrected":
            continue
        plan = plan_query(all_q[qid])
        key_names = [k for k, _ in plan.keys]
        gold_rows = execute(gold_conn, all_q[qid])
        norm = lambda v: str(int(float(v))) if num(v) is not None and float(v).is_integer() else str(v).strip().lower()  # noqa: E731
        gindex = {tuple(norm(r.get(k)) for k in key_names): r for r in gold_rows}
        for r in a["rows"]:
            g = gindex.get(tuple(norm(r[k]) for k in key_names))
            if g is None:
                continue
            for name, (lo, hi) in r["__ci"].items():
                gv = num(g.get(name))
                if gv is None or r.get(name) is None:
                    continue
                coverage.append({"query_id": qid, "cell": name, "covered": lo - 1e-9 <= gv <= hi + 1e-9,
                                 "estimate": r[name], "gold": gv, "lo": lo, "hi": hi})
                if abs(gv) > 0:
                    widths.append((hi - lo) / 2 / abs(gv))

    def summary(ids: set[str]) -> dict[str, Any]:
        ids = sorted(ids)
        mean = lambda s: sum(scores[s][i] for i in ids) / len(ids) if ids else None  # noqa: E731
        d = [scores["corrected"][i] - scores["proxy"][i] for i in ids]
        rng = random.Random(0)
        boots = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(5000)) if d else [0.0]
        return {"n": len(ids), "proxy": mean("proxy"), "null_oracle": mean("null_oracle"), "corrected": mean("corrected"),
                "diff": sum(d) / len(d) if d else None, "ci95": [boots[125], boots[4875]] if d else None,
                "better": sum(x > 1e-12 for x in d), "worse": sum(x < -1e-12 for x in d)}

    corrected_ids = {qid for qid, a in answers.items() if a.get("mode") == "corrected"}
    train_ids = {r["query_id"] for r in train}
    report = {
        "audit_only": True,
        "design": json.loads((out / "design.json").read_text()),
        "oracle_tokens": sum(r["tokens"] for r in cache.values()),
        "q1_per_document": audit,
        "q2_queries": {"corrected_all": summary(corrected_ids),
                       "corrected_input": summary(corrected_ids & train_ids),
                       "corrected_held_out": summary(corrected_ids - train_ids),
                       "all_80": summary(set(all_q))},
        "not_corrected": {qid: a.get("reason") or "no oracle column" for qid, a in answers.items() if a.get("mode") != "corrected"},
        "ci_coverage": {"cells": len(coverage), "covered": sum(c["covered"] for c in coverage) / max(1, len(coverage)),
                        "median_relative_half_width": sorted(widths)[len(widths) // 2] if widths else None},
        "coverage_cells": coverage,
        "per_query": {qid: {v: round(scores[v][qid], 4) for v in scores} for qid in sorted(all_q)},
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: report[k] for k in ("oracle_tokens", "q1_per_document", "q2_queries", "ci_coverage")}, indent=2, default=str))
    print("not corrected:", len(report["not_corrected"]), "e.g.", list(report["not_corrected"].items())[:4])
    return 0


if __name__ == "__main__":
    sys.exit(main())

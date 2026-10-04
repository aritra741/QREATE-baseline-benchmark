"""Phase 2 analyses of the experiment plan (results/drift_design/EXPERIMENT_PLAN.md). No model calls: everything is
read from the replayed streams (results/experiments/E2-replay, every query's view kept) and the read journals.

  components  E2.4  per query and system: structure F2, cell F1@0.20, predicted rows and a failure label
                    (no rows / structure / values / ok), for static, every unlimited and budgeted stream, and DocETL
  patches     E2.2 + E4.1  every patch: tokens, estimated tokens, columns, gain on the query that triggered it, later
                    queries that use its columns and their gain over static; the share of patch tokens with no gain
  order       E2.3  the same query at the same drift level across budgets: where its view differs, whether the
                    differing cells were read in only one stream (scope / skipped) or read in both with different
                    values (the patch prompt differed)
  reads       E1.1 + E1.2  shared-read responses compared cell by cell: OpenRouter, Ollama 4-bit, its repeats, 16-bit
  variance    E1.1  repeated runs' scores side by side, with bootstrap intervals over queries

Outputs go to results/experiments/<experiment>/ (JSON for the numbers, CSV for per-row tables); every command
is resumable (cached per query and view digest) and can be re-run after more streams finish.

    python -m quwarts.eval.exp_analysis components --corpus legal
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sqlite3
from pathlib import Path

from quwarts.eval import drift_run as R

REPO = R.RESULTS.parent
EXP = REPO / "results" / "experiments"
STATUS_PATH = EXP / "status.jsonl"
REPLAY = EXP / "E2-replay" / "live"
REPLAY_SCRATCH = Path("/scratch/general/vast/u1592362/quwarts_exp/E2-replay/drift_live_ollama")
LEVELS = (0, 25, 50, 75, 100)
BUDGETS = (10, 25, 50, 75, 100)


def streams(corpus: str) -> dict[str, list[dict]]:
    """Replayed stream records by key (``fixed4-attribute_pool/100``, ``fixed4b025-attribute_pool/100``, ...)."""

    out = {}
    for f in sorted((REPLAY / corpus / "streams").glob("fixed4*-attribute_pool_*.jsonl")):
        key = f.stem.replace("attribute_pool_", "attribute_pool/")
        out[key] = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
    return out


def view(corpus: str, key: str, pos: int) -> Path:
    return REPLAY_SCRATCH / corpus / key.replace("/", "_") / "views" / f"{pos:03d}.db"


def budget_of(key: str) -> int | None:
    head = key.split("-")[0]
    return int(head[len("fixed4b"):]) if head.startswith("fixed4b") else None


def level_of(key: str) -> int:
    return int(key.split("/")[1])


def bootstrap(xs: list[float], reps: int = 5000, seed: int = 0) -> list[float]:
    if not xs:
        return [0.0, 0.0]
    rng = random.Random(seed)
    ms = sorted(sum(rng.choice(xs) for _ in xs) / len(xs) for _ in range(reps))
    return [round(ms[int(0.025 * reps)], 4), round(ms[int(0.975 * reps)], 4)]


# ------------------------------------------------------------------------------------------ E2.4 components

def score_components(corpus: str, items: list[tuple[str, Path]], cache: dict) -> None:
    """structure F2, cell F1@0.20 and predicted rows of every (query, view) not yet in ``cache``."""

    from quwarts.core.pipeline import official_sql
    from quwarts.eval.router_execute_v3 import DATASET
    from quwarts.experiments.synthesize_case80 import score_with_rewrites

    ctx = R.context(corpus)
    gold = R.Scorer(corpus).gold()[0]
    todo = {}
    for q, db in items:
        k = f"{q}|{R.digest(db, ctx.catalog[q])}"
        if k not in cache and k not in todo:
            todo[k] = (q, db)
    keys = list(todo)
    for i in range(0, len(keys), 8):
        chunk = {k: todo[k] for k in keys[i:i + 8]}
        rows = [{"query_id": k, "sql": ctx.catalog[q], "pack": q.split(":", 1)[0]} for k, (q, _db) in chunk.items()]
        rewrites = {k: {"sql": official_sql(ctx.catalog[q], str(db), R.predicates(corpus), query_id=k), "sqlite_path": str(db)}
                    for k, (q, db) in chunk.items()}
        rep = score_with_rewrites(rows, rewrites, Path(next(iter(chunk.values()))[1]), gold, DATASET[ctx.spec.name])
        by = {r["query_id"]: r for r in rep.get("per_query") or []}
        for k in chunk:
            r = by.get(k, {})
            cache[k] = {"structure_f2": float(r.get("structure_f2") or 0.0), "cell_f1_20": float(r.get("cell_f1_20") or 0.0),
                        "pred_rows": r.get("pred_rows"), "gold_rows": r.get("gold_rows")}


def label(c: dict) -> str:
    if not c["pred_rows"]:
        return "no rows"
    if c["structure_f2"] < 0.999:
        return "structure"
    if c["cell_f1_20"] < 0.999:
        return "values"
    return "ok"


def components(corpus: str) -> dict:
    out_dir = EXP / "E2.4-errors" / corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_path = out_dir / "components_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    ctx = R.context(corpus)
    st = streams(corpus)
    static = REPLAY_SCRATCH / corpus / "static.db"
    systems: dict[str, list[tuple[str, Path]]] = {}
    for key, recs in st.items():
        b = budget_of(key)
        name = f"{'unlimited' if b is None else f'budget{b:03d}'}@{level_of(key)}"
        systems[name] = [(r["qid"], view(corpus, key, r["pos"])) for r in recs]
    if "fixed4-attribute_pool/100" in st:
        systems["static@100"] = [(r["qid"], static) for r in st["fixed4-attribute_pool/100"]]
    for name, items in systems.items():
        score_components(corpus, [(q, db) for q, db in items if db.exists()], cache)
        cache_path.write_text(json.dumps(cache))
    rows, summary = [], {}
    for name, items in systems.items():
        comps = []
        for q, db in items:
            if not db.exists():
                continue
            c = cache[f"{q}|{R.digest(db, ctx.catalog[q])}"]
            comps.append(c)
            rows.append({"system": name, "qid": q, **c, "product": round(c["structure_f2"] * c["cell_f1_20"], 4),
                         "label": label(c)})
        if comps:
            labels = [label(c) for c in comps]
            summary[name] = {"n": len(comps),
                             "structure_f2": round(sum(c["structure_f2"] for c in comps) / len(comps), 4),
                             "cell_f1_20": round(sum(c["cell_f1_20"] for c in comps) / len(comps), 4),
                             "labels": {k: labels.count(k) for k in ("no rows", "structure", "values", "ok")}}
    docetl = REPO / "results" / "docetl_drift_ollama" / corpus / "per_query.json"
    if docetl.exists():
        summary["docetl (as recorded)"] = {"per_query_file": str(docetl.relative_to(REPO))}
    with (out_dir / "per_query.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]) if rows else ["system"])
        w.writeheader()
        w.writerows(rows)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


# ------------------------------------------------------------------------------------------ E2.2 / E4.1 patches

def patches(corpus: str) -> dict:
    from quwarts.core.adapt import controller as C

    out_dir = EXP / "E2.2-patches" / corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = R.context(corpus)
    rows, per_stream = [], {}
    for key, recs in streams(corpus).items():
        needs = []
        for r in recs:
            need = C.query_attributes(ctx.spec, r["qid"], ctx.catalog[r["qid"]], {r["qid"]: ctx.catalog[r["qid"]]})
            needs.append({f"{t}.{a}" for t, attrs in need.items() for a in attrs})
        tok_total = wasted = 0
        for i, r in enumerate(recs):
            if r["action"] != "patch":
                continue
            cols = sorted(r.get("fetched", {}))
            later = [j for j in range(i + 1, len(recs)) if needs[j] & set(cols)]
            gain = r["benchmark"] - r["static_benchmark"]
            later_gain = sum(recs[j]["benchmark"] - recs[j]["static_benchmark"] for j in later)
            tokens = r["input_tokens"] + r["output_tokens"]
            no_value = gain <= 0 and all(recs[j]["benchmark"] <= recs[j]["static_benchmark"] for j in later)
            tok_total += tokens
            wasted += tokens if no_value else 0
            rows.append({"stream": key, "budget": budget_of(key), "level": level_of(key), "pos": r["pos"], "qid": r["qid"],
                         "columns": ";".join(cols), "docs_read": r["docs_read"], "tokens": tokens,
                         "est_tokens": r.get("est_tokens"), "gain_on_query": round(gain, 4),
                         "later_queries_using": len(later), "later_gain_sum": round(later_gain, 4),
                         "no_value": no_value})
        per_stream[key] = {"patch_tokens": tok_total, "no_value_tokens": wasted,
                           "no_value_share": round(wasted / tok_total, 3) if tok_total else None}
    est = [(r["est_tokens"], r["tokens"]) for r in rows if r["est_tokens"]]
    ratios = sorted(e / t for e, t in est if t)
    cal = {"patches_with_estimate": len(est),
           "median_est_over_actual": round(ratios[len(ratios) // 2], 3) if ratios else None,
           "p10_p90": [round(ratios[int(0.1 * len(ratios))], 3), round(ratios[int(0.9 * len(ratios))], 3)] if ratios else None}
    with (out_dir / "patches.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]) if rows else ["stream"])
        w.writeheader()
        w.writerows(rows)
    out = {"streams": per_stream, "cost_calibration": cal}
    (out_dir / "summary.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------------------------------ E2.3 order effects

def cells(db: Path, table: str, cols: list[str]) -> dict[tuple, tuple]:
    conn = sqlite3.connect(db)
    try:
        have = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        use = [c for c in cols if c in have]
        if "doc_id" not in have or not use:
            return {}
        q = f'SELECT doc_id, {", ".join(chr(34) + c + chr(34) for c in use)} FROM "{table}"'
        return {(row[0], c): v for row in conn.execute(q) for c, v in zip(use, row[1:])}
    finally:
        conn.close()


def order(corpus: str) -> dict:
    from quwarts.core.adapt import controller as C

    out_dir = EXP / "E2.3-order" / corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = R.context(corpus)
    st = streams(corpus)
    rows = []
    for p in LEVELS:
        keys = [k for k in st if level_of(k) == p]
        base = f"fixed4-attribute_pool/{p}"
        if base not in st:
            continue
        for k in keys:
            if k == base:
                continue
            for a, b in zip(st[base], st[k]):
                if a["benchmark"] == b["benchmark"]:
                    continue
                need = C.query_attributes(ctx.spec, a["qid"], ctx.catalog[a["qid"]], {a["qid"]: ctx.catalog[a["qid"]]})
                va, vb = view(corpus, base, a["pos"]), view(corpus, k, b["pos"])
                only_one = both_differ = same = 0
                for t, attrs in need.items():
                    ca, cb = cells(va, t, sorted(attrs)), cells(vb, t, sorted(attrs))
                    for cell_key in set(ca) | set(cb):
                        x, y = ca.get(cell_key), cb.get(cell_key)
                        if x == y:
                            same += 1
                        elif x is None or y is None:
                            only_one += 1
                        else:
                            both_differ += 1
                rows.append({"level": p, "stream": k, "pos": a["pos"], "qid": a["qid"],
                             "action_unlimited": a["action"], "action_budget": b["action"],
                             "score_unlimited": a["benchmark"], "score_budget": b["benchmark"],
                             "cells_same": same, "cells_read_in_one_only": only_one, "cells_read_in_both_differ": both_differ})
    with (out_dir / "differences.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]) if rows else ["level"])
        w.writeheader()
        w.writerows(rows)
    better = [r for r in rows if r["score_budget"] > r["score_unlimited"]]
    out = {"queries_differing": len(rows), "budget_scores_higher": len(better),
           "of_those_answered_without_own_patch": sum(r["action_budget"] != "patch" for r in better),
           "cells_read_in_one_only": sum(r["cells_read_in_one_only"] for r in rows),
           "cells_read_in_both_differ": sum(r["cells_read_in_both_differ"] for r in rows)}
    (out_dir / "summary.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------------------------------ E1.1 / E1.2 reads

def parse(response: str) -> dict:
    t = response.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    try:
        d = json.loads(t)
        return d.get("fields", d) if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def reads() -> dict:
    out_dir = EXP / "E1-reads"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = REPO / "results" / "quwarts_router_v3"
    runs = {"openrouter": base / "player", "ollama_q4": base / "player_ollama",
            "ollama_q4_rep1": base / "player_ollama_rep1", "ollama_q4_rep2": base / "player_ollama_rep2",
            "ollama_fp16": base / "player_ollama_fp16"}
    vals, scores = {}, {}
    for name, d in runs.items():
        j = d / "shared_read_protocol" / "reads.jsonl"
        if not j.exists():
            continue
        vals[name] = {}
        for line in j.read_text().splitlines():
            r = json.loads(line)
            for a, v in parse(r["response"]).items():
                vals[name][(r["table"], r["doc"], a)] = v
        s = d / "shared_read_protocol" / "score_blank.json"
        if s.exists():
            sb = json.loads(s.read_text())
            pq = [x["product"] for x in sb["read_first"]["per_query"]]
            held = sb["read_first"]["held_out_split"]
            scores[name] = {"held_out": round(held["product"], 4), "structure_f2": round(held["structure_f2"], 4),
                            "cell_f1_20": round(held["cell_f1_20"], 4), "read_tokens": sb["read_tokens"],
                            "all_100_mean": round(sum(pq) / len(pq), 4), "all_100_ci": bootstrap(pq)}
    agree = {}
    names = list(vals)
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            keys = set(vals[x]) & set(vals[y])
            same = sum(str(vals[x][k]).strip().lower() == str(vals[y][k]).strip().lower() for k in keys)
            agree[f"{x} vs {y}"] = {"cells": len(keys), "identical": same,
                                    "share_identical": round(same / len(keys), 3) if keys else None}
    if "openrouter" in vals and "ollama_q4" in vals:
        diffs = [{"table": t, "doc": d, "attribute": a, "openrouter": vals["openrouter"][(t, d, a)],
                  "ollama_q4": vals["ollama_q4"][(t, d, a)], "ollama_fp16": vals.get("ollama_fp16", {}).get((t, d, a))}
                 for (t, d, a) in sorted(set(vals["openrouter"]) & set(vals["ollama_q4"]))
                 if str(vals["openrouter"][(t, d, a)]).strip().lower() != str(vals["ollama_q4"][(t, d, a)]).strip().lower()]
        with (out_dir / "openrouter_vs_ollama_cells.csv").open("w", newline="") as h:
            w = csv.DictWriter(h, fieldnames=["table", "doc", "attribute", "openrouter", "ollama_q4", "ollama_fp16"])
            w.writeheader()
            w.writerows(diffs)
    out = {"scores": scores, "cell_agreement": agree}
    (out_dir / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    return out


def variance() -> dict:
    out_dir = EXP / "E1-variance"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = {}
    for corpus in ("cspaper", "player"):
        orig = REPO / "results" / "drift_live_ollama" / corpus / "streams" / "fixed4-attribute_pool_100.jsonl"
        rep = EXP / f"E1.1-stream-rep-{corpus}" / "live" / corpus / "streams" / "fixed4-attribute_pool_100.jsonl"
        runs = {"recorded": orig, "repeat": rep}
        if corpus == "player":
            runs["fp16"] = EXP / "E1.2-stream-fp16-player" / "live" / corpus / "streams" / "fixed4-attribute_pool_100.jsonl"
        res = {}
        for name, f in runs.items():
            if f.exists():
                recs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
                xs = [r["benchmark"] for r in recs]
                res[name] = {"mean": round(sum(xs) / len(xs), 4), "ci": bootstrap(xs),
                             "patch_tokens": sum(r["input_tokens"] + r["output_tokens"] for r in recs),
                             "per_query": {r["qid"]: r["benchmark"] for r in recs}}
        if "recorded" in res and "repeat" in res:
            a, b = res["recorded"]["per_query"], res["repeat"]["per_query"]
            d = [b[q] - a[q] for q in a if q in b]
            res["repeat_minus_recorded"] = {"mean": round(sum(d) / len(d), 4), "ci": bootstrap(d),
                                            "queries_changed": sum(abs(x) > 1e-9 for x in d)}
        for v in res.values():
            v.pop("per_query", None)
        out[corpus] = res
    (out_dir / "summary.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------------------------------ per-column accuracy

NULLS = {"", "null", "none", "n/a", "na", "nan", "not applicable", "not specified", "unknown", "not mentioned"}


def is_null(v) -> bool:
    return v is None or str(v).strip().lower() in NULLS


def same_value(x, y) -> bool:
    """Equal after normalization; numbers within 20% (as cell F1@0.20)."""

    from quwarts.core.router.comparator import as_number

    a, b = as_number(x), as_number(y)
    if a is not None and b is not None:
        return abs(a - b) <= 0.2 * max(abs(a), abs(b)) if (a or b) else True
    return str(x).strip().lower() == str(y).strip().lower()


def parts(v) -> set[str]:
    """A value's parts, normalized: split on '||' / ';' / ',', lowercased, dashes and spaces unified."""

    import re

    t = str(v).lower().replace("\u2013", "-").replace("\u2014", "-")
    return {re.sub(r"\s+", " ", p).strip(" .") for p in re.split(r"\|\||;|,", t) if p.strip(" .")}


def lenient(x, y) -> bool:
    """Same value allowing list order, extra or missing list items (any shared part), case, dashes, spacing."""

    if same_value(x, y):
        return True
    a, b = parts(x), parts(y)
    return bool(a & b)


def gold_by_doc(corpus: str) -> dict[str, dict[str, dict]]:
    """Gold row of every document, by table: cspaper by ``pdf_filename``, the others by ``id`` (as a number)."""

    gold = R.Scorer(corpus).gold()[0]
    ctx = R.context(corpus)
    out = {}
    for t, rows in gold.items():
        if t not in ctx.names:
            continue
        key = "pdf_filename" if "pdf_filename" in rows[0] else "id"

        def norm(v) -> str:  # a file name without its extension (arXiv names have dots); an id as a number
            v = str(v).strip()
            for ext in (".pdf", ".txt"):
                v = v[: -len(ext)] if v.endswith(ext) else v
            return str(int(v)) if v.isdigit() else v

        by = {norm(r[key]): r for r in rows if r.get(key) not in (None, "")}
        out[t] = {d: by[norm(d)] for d in ctx.names[t] if norm(d) in by}
    return out


def columns(corpus: str, key: str = "fixed4-attribute_pool/100") -> dict:
    """Per column, on the documents the stream read: how often the model fills a value where gold has none
    (false fill), leaves one empty where gold has one (miss), and agrees with gold where both have one. From the
    stream's master database (build + patches, raw values) and its record of which documents each column was
    read for."""

    out_dir = EXP / "E2.1-columns" / corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = R.context(corpus)
    gold = gold_by_doc(corpus)
    state = json.loads((REPLAY / corpus / "state" / f"{key.replace('/', '_')}.json").read_text())
    master = REPLAY_SCRATCH / corpus / key.replace("/", "_") / "master.db"
    build_cols = {f"{t}.{a}" for t, a, _d in json.loads((REPLAY / corpus / "state" / "fixed4-attribute_pool_0.json")
                                                         .read_text())["mat"]} if (REPLAY / corpus / "state" /
                                                         "fixed4-attribute_pool_0.json").exists() else set()
    patched = {c for r in state["records"] for c in r.get("fetched", {})}
    conn = sqlite3.connect(master)
    rows = []
    for t, a, docs in state["mat"]:
        have = {r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')}
        if a not in have or t not in gold:
            continue
        got = dict(conn.execute(f'SELECT doc_id, "{a}" FROM "{t}"').fetchall())
        got = {(k if str(k).endswith(".txt") or t not in ("cspaper",) else k): v for k, v in got.items()}
        n = gn = pn = ff = miss = both = agree = loose = 0
        for d in docs:
            g = gold[t].get(d)
            if g is None or a not in g:
                continue
            v = got.get(d, got.get(d.rsplit(".", 1)[0]))
            n += 1
            gnull, pnull = is_null(g[a]), is_null(v)
            gn += gnull
            pn += pnull
            if gnull and not pnull:
                ff += 1
            elif pnull and not gnull:
                miss += 1
            elif not gnull and not pnull:
                both += 1
                agree += same_value(v, g[a])
                loose += lenient(v, g[a])
        if n:
            rows.append({"column": f"{t}.{a}", "source": "patch" if f"{t}.{a}" in patched else "build",
                         "docs_matched": n, "gold_null_share": round(gn / n, 3), "pred_null_share": round(pn / n, 3),
                         "false_fill_rate": round(ff / gn, 3) if gn else None, "miss_rate": round(miss / (n - gn), 3) if n - gn else None,
                         "agree_when_both": round(agree / both, 3) if both else None,
                         "lenient_agree_when_both": round(loose / both, 3) if both else None,
                         "gold_null": gn, "false_fills": ff})
    conn.close()
    with (out_dir / "columns.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]) if rows else ["column"])
        w.writeheader()
        w.writerows(rows)
    tot_gn = sum(r["gold_null"] for r in rows)
    out = {"stream": key, "columns": len(rows), "gold_null_cells": tot_gn,
           "false_fill_rate_overall": round(sum(r["false_fills"] for r in rows) / tot_gn, 3) if tot_gn else None,
           "by_source": {src: {"columns": len([r for r in rows if r["source"] == src]),
                               "false_fill_rate": round(sum(r["false_fills"] for r in rows if r["source"] == src) /
                                                        max(1, sum(r["gold_null"] for r in rows if r["source"] == src)), 3),
                               "agree_when_both_mean": round(sum(r["agree_when_both"] or 0 for r in rows if r["source"] == src) /
                                                             max(1, len([r for r in rows if r["source"] == src])), 3)}
                         for src in ("build", "patch")}}
    (out_dir / "summary.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------------------------------ E8 canonicalization

def literals(sql: str) -> dict[str, set[str]]:
    """String constants each column is compared with (=, IN, LIKE with the % removed), by lowercase column name."""

    import sqlglot
    from sqlglot import exp

    out: dict[str, set[str]] = {}
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:  # noqa: BLE001
        return out
    for node in tree.find_all(exp.EQ, exp.NEQ, exp.In, exp.Like, exp.ILike):
        cols = list(node.find_all(exp.Column))
        lits = [l.this for l in node.find_all(exp.Literal) if l.is_string]
        if len(cols) == 1 and lits:
            out.setdefault(cols[0].name.lower(), set()).update(x.strip("%") for x in lits if x.strip("%"))
    return out


def canon_key(v: str) -> str:
    import re

    t = str(v).lower().replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"[^a-z0-9]+", "", t)


def to_vocab(part: str, vocab: list[str]) -> str:
    """The vocabulary label a value part means: same normalized form, else a close spelling (difflib >= 0.85, or
    one is a prefix of the other with at least 5 shared characters, e.g. Surrealist / Surrealism); else unchanged."""

    import difflib

    k = canon_key(part)
    if not k:
        return part
    by = {canon_key(x): x for x in vocab}
    if k in by:
        return by[k]
    best = max(vocab, key=lambda x: difflib.SequenceMatcher(None, k, canon_key(x)).ratio(), default=None)
    if best is not None:
        bk = canon_key(best)
        common = len(next((k[:i] for i in range(min(len(k), len(bk)), 0, -1) if k[:i] == bk[:i]), ""))
        if difflib.SequenceMatcher(None, k, bk).ratio() >= 0.85 or (common >= 5 and common >= min(len(k), len(bk)) - 3):
            return best
    return part


def canonicalize_view(src: Path, dest: Path, vocab: dict[tuple[str, str], list[str]]) -> int:
    import shutil

    shutil.copy2(src, dest)
    conn = sqlite3.connect(dest)
    n = 0
    with conn:
        for (t, c), words in vocab.items():
            try:
                rows = conn.execute(f'SELECT rowid, "{c}" FROM "{t}"').fetchall()
            except sqlite3.OperationalError:
                continue
            for rowid, v in rows:
                if not isinstance(v, str) or not v.strip():
                    continue
                new = " || ".join(dict.fromkeys(to_vocab(p.strip(), words) for p in v.split("||")))
                if new != v:
                    conn.execute(f'UPDATE "{t}" SET "{c}" = ? WHERE rowid = ?', (new, rowid))
                    n += 1
    conn.close()
    return n


def canon(corpus: str) -> dict:
    """E8: canonicalize each query's served view to the column vocabulary known when the query arrives (declared
    allowed values + string constants of the build workload and the queries so far), then re-score. Unlimited and
    10% budget streams at 0% and 100% drift. No model calls."""

    out_dir = EXP / "E8-canon" / corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = REPLAY_SCRATCH.parent / "E8-canon" / corpus
    tmp.mkdir(parents=True, exist_ok=True)
    ctx = R.context(corpus)
    fields = ctx.fields
    st = streams(corpus)
    cache_path = out_dir / "components_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    summary = {}
    for key in ("fixed4-attribute_pool/0", "fixed4-attribute_pool/100", "fixed4b010-attribute_pool/100"):
        if key not in st:
            continue
        build_wl = dict(ctx.w0)
        seen_lits: dict[str, set[str]] = {}
        for sql in build_wl.values():
            for c, ls in literals(sql).items():
                seen_lits.setdefault(c, set()).update(ls)
        items_raw, items_canon, changed = [], [], 0
        for r in st[key]:
            for c, ls in literals(ctx.catalog[r["qid"]]).items():
                seen_lits.setdefault(c, set()).update(ls)
            vocab = {}
            for q, f in fields.items():
                t, c = q.split(".", 1)
                words = sorted(set(f.choices or []) | seen_lits.get(c.lower(), set()))
                if words and f.value_type not in ("int", "float"):
                    vocab[(t, c)] = words
            src = view(corpus, key, r["pos"])
            if not src.exists():
                continue
            dest = tmp / f"{key.replace('/', '_')}_{r['pos']:03d}.db"
            if not dest.exists():
                changed += canonicalize_view(src, dest, vocab)
            items_raw.append((r["qid"], src))
            items_canon.append((r["qid"], dest))
        score_components(corpus, items_raw + items_canon, cache)
        cache_path.write_text(json.dumps(cache))

        def mean(items):
            cs = [cache[f"{q}|{R.digest(db, ctx.catalog[q])}"] for q, db in items]
            prod = [c["structure_f2"] * c["cell_f1_20"] for c in cs]
            return {"score": round(sum(prod) / len(prod), 4), "structure_f2": round(sum(c["structure_f2"] for c in cs) / len(cs), 4),
                    "cell_f1_20": round(sum(c["cell_f1_20"] for c in cs) / len(cs), 4), "per_query": prod}

        a, b = mean(items_raw), mean(items_canon)
        d = [y - x for x, y in zip(a.pop("per_query"), b.pop("per_query"))]
        summary[key] = {"raw": a, "canonicalized": b, "cells_rewritten": changed,
                        "diff_mean": round(sum(d) / len(d), 4), "diff_ci": bootstrap(d),
                        "queries_up": sum(x > 1e-9 for x in d), "queries_down": sum(x < -1e-9 for x in d)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


# ------------------------------------------------------------------------------------------ E3 policies

def policies(corpus: str) -> dict:
    """Budget policies side by side: score and tokens per budget and drift level, for the recorded sweep (fcfs) and
    every finished E3.2-<policy> run; whether score rises with budget at each level; unlimited and static for scale."""

    src = REPO / "results" / "drift_live_ollama" / corpus / "streams"
    runs = {"fcfs": src}
    for d in sorted(EXP.glob("E3.2-*")):
        runs[d.name.split("-", 1)[1]] = d / "live" / corpus / "streams"
    out: dict = {}

    def stats(f: Path):
        rs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
        return round(sum(r["benchmark"] for r in rs) / len(rs), 4), sum(r["input_tokens"] + r["output_tokens"] for r in rs)

    for name, d in runs.items():
        cells = {}
        for p in LEVELS:
            for b in BUDGETS:
                f = d / f"fixed4b{b:03d}-attribute_pool_{p}.jsonl"
                if f.exists():
                    cells[f"{b}@{p}"] = stats(f)
        if not cells:
            continue
        mono = {}
        for p in LEVELS:
            ys = [cells[f"{b}@{p}"][0] for b in BUDGETS if f"{b}@{p}" in cells]
            if len(ys) == len(BUDGETS):
                mono[p] = all(y2 >= y1 - 0.002 for y1, y2 in zip(ys, ys[1:]))  # within stream noise
        out[name] = {"cells": cells, "monotone_by_level": mono,
                     "mean_score": round(sum(v[0] for v in cells.values()) / len(cells), 4),
                     "total_tokens": sum(v[1] for v in cells.values()), "streams": len(cells)}
    for p in LEVELS:
        f = src / f"fixed4-attribute_pool_{p}.jsonl"
        if f.exists():
            rs = [json.loads(line) for line in f.read_text().splitlines()]
            out.setdefault("unlimited", {})[p] = round(sum(r["benchmark"] for r in rs) / len(rs), 4)
            out.setdefault("static", {})[p] = round(sum(r["static_benchmark"] for r in rs) / len(rs), 4)
    out_dir = EXP / "E3-policies" / corpus
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(out, indent=1))
    return out


# ------------------------------------------------------------------------------------------ E9 query types

def query_features(sql: str, fields: dict) -> dict:
    """Structural features of one query: grouping, joins, aggregations (over text or numbers), filters."""

    import sqlglot
    from sqlglot import exp

    try:
        t = sqlglot.parse_one(sql, read="sqlite")
    except Exception:  # noqa: BLE001
        return {"parse_error": True}
    numeric = {k.split(".", 1)[1] for k, f in fields.items() if f.value_type in ("int", "float")}
    aggs = []
    for kind, cls in (("count", exp.Count), ("sum", exp.Sum), ("avg", exp.Avg), ("min", exp.Min), ("max", exp.Max)):
        for node in t.find_all(cls):
            cols = [c.name for c in node.find_all(exp.Column)]
            if kind in ("min", "max"):
                kind2 = f"{kind}_text" if cols and not all(c in numeric for c in cols) else f"{kind}_num"
            else:
                kind2 = kind
            aggs.append(kind2)
    where = t.find(exp.Where)
    preds = list(where.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In, exp.Like, exp.ILike)) if where else []
    filt = set()
    for pr in preds:
        if isinstance(pr, (exp.Like, exp.ILike)):
            filt.add("like")
        elif isinstance(pr, exp.In):
            filt.add("in")
        elif any(l.is_string for l in pr.find_all(exp.Literal)):
            filt.add("string_eq" if isinstance(pr, (exp.EQ, exp.NEQ)) else "string_cmp")
        else:
            filt.add("numeric_cmp")
    return {"group_by": t.find(exp.Group) is not None, "joins": len(list(t.find_all(exp.Join))),
            "aggs": sorted(set(aggs)), "n_aggs": len(aggs), "filter_kinds": sorted(filt), "n_predicates": len(preds),
            "having": t.find(exp.Having) is not None, "order_limit": t.find(exp.Order) is not None or t.find(exp.Limit) is not None,
            "distinct": t.find(exp.Distinct) is not None, "case": t.find(exp.Case) is not None,
            "n_tables": len({tb.name for tb in t.find_all(exp.Table)})}


def query_types(corpora: list[str]) -> dict:
    """E9: scores by query type (structure F2 and cell F1 from E2.4 where available), per corpus and pooled."""

    out_dir = EXP / "E9-query-types"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for corpus in corpora:
        ctx = R.context(corpus)
        src = REPO / "results" / "drift_live_ollama" / corpus / "streams"
        recs = {p: {r["qid"]: r for r in map(json.loads, (src / f"fixed4-attribute_pool_{p}.jsonl").read_text().splitlines())}
                for p in (0, 100)}
        bud = {b: {r["qid"]: r for r in map(json.loads, (src / f"fixed4b{b:03d}-attribute_pool_100.jsonl").read_text().splitlines())}
               for b in (25, 50)}
        comp = {}
        pq = EXP / "E2.4-errors" / corpus / "per_query.csv"
        if pq.exists():
            for r in csv.DictReader(pq.open()):
                comp[(r["system"], r["qid"])] = r
        docetl_path = REPO / "results" / "docetl_drift_ollama" / corpus / "per_query.json"
        docetl = json.loads(docetl_path.read_text()) if docetl_path.exists() else {}
        for qid, r in recs[100].items():
            f = query_features(ctx.catalog[qid], ctx.fields)
            c = comp.get(("unlimited@100", qid), {})
            rows.append({"corpus": corpus, "qid": qid, **f,
                         "static_100": r["static_benchmark"], "adaptive_0": recs[0].get(qid, {}).get("benchmark"),
                         "adaptive_100": r["benchmark"], "budget25_100": bud[25].get(qid, {}).get("benchmark"),
                         "budget50_100": bud[50].get(qid, {}).get("benchmark"),
                         "docetl": docetl.get(qid, {}).get("benchmark") if isinstance(docetl.get(qid), dict) else None,
                         "structure_f2_100": float(c["structure_f2"]) if c else None,
                         "cell_f1_100": float(c["cell_f1_20"]) if c else None,
                         "patch_tokens_100": r["input_tokens"] + r["output_tokens"] if r["action"] == "patch" else 0})

    def bucket(r: dict) -> dict[str, str]:
        aggs = r.get("aggs", [])
        return {
            "group_by": "GROUP BY" if r.get("group_by") else "no GROUP BY",
            "joins": {0: "0 joins", 1: "1 join"}.get(r.get("joins", 0), "2+ joins"),
            "aggregation": ("MIN/MAX over text" if any(a.endswith("_text") for a in aggs) else
                            "AVG/SUM" if any(a in ("avg", "sum") for a in aggs) else
                            "MIN/MAX over numbers" if any(a.endswith("_num") for a in aggs) else
                            "COUNT only" if aggs else "no aggregation"),
            "filter": ("no filter" if not r.get("filter_kinds") else
                       "LIKE" if "like" in r["filter_kinds"] else
                       "string = / IN" if set(r["filter_kinds"]) & {"string_eq", "in"} else "numeric only"),
            "predicates": {0: "0 predicates", 1: "1 predicate", 2: "2 predicates"}.get(r.get("n_predicates", 0), "3+ predicates"),
            "extras": "HAVING / ORDER / LIMIT / CASE" if (r.get("having") or r.get("order_limit") or r.get("case")) else "none"}

    metrics = ["static_100", "adaptive_0", "adaptive_100", "budget25_100", "budget50_100", "docetl",
               "structure_f2_100", "cell_f1_100", "patch_tokens_100"]
    summary: dict = {}
    for scope in ["all"] + corpora:
        sel = [r for r in rows if scope == "all" or r["corpus"] == scope]
        summary[scope] = {}
        for dim in ("group_by", "joins", "aggregation", "filter", "predicates", "extras"):
            groups: dict[str, list] = {}
            for r in sel:
                groups.setdefault(bucket(r)[dim], []).append(r)
            summary[scope][dim] = {}
            for g, rs in sorted(groups.items()):
                entry = {"n": len(rs)}
                for m in metrics:
                    xs = [r[m] for r in rs if r.get(m) is not None]
                    if xs:
                        entry[m] = round(sum(xs) / len(xs), 4) if m != "patch_tokens_100" else round(sum(xs) / 1e6, 2)
                        if m == "docetl":
                            entry["docetl_n"] = len(xs)
                entry["adaptive_100_ci"] = bootstrap([r["adaptive_100"] for r in rs])
                summary[scope][dim][g] = entry
    with (out_dir / "per_query.csv").open("w", newline="") as h:
        keys = sorted({k for r in rows for k in r})
        w = csv.DictWriter(h, fieldnames=keys)
        w.writeheader()
        w.writerows([{k: (json.dumps(v) if isinstance(v, list) else v) for k, v in r.items()} for r in rows])
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


# ------------------------------------------------------------------------------------------ accounting

def accounting() -> dict:
    """Every model call of every run: calls, input and output tokens, and latency where it was logged.

    Sources, by what they record:
      drift_live usage.jsonl (per call: input, output, seconds) — recorded runs and every experiment root; in a cloned
        root only rows whose prompt is not in the recorded run's usage are new calls of that experiment;
      read journals with only a total per call (shared reads, prompt width, planner probes and executions):
        output = the response re-counted with the Qwen 2.5 tokenizer (as the Ollama client counts), input = total − output;
        no per-call latency (the step's wall-clock time, from status.jsonl, is reported instead);
      runner usage logs (results/experiments/usage/<step>.jsonl; per call, from 2026-10-02 13:15);
      DocETL per_query.json (per query: prompt and completion tokens, seconds).
    """

    from quwarts.core.retrieve_extract.tokens import count_tokens

    def lat(xs: list[float]) -> dict:
        if not xs:
            return {}
        xs = sorted(xs)
        return {"mean_s": round(sum(xs) / len(xs), 2), "p50_s": round(xs[len(xs) // 2], 2),
                "p95_s": round(xs[int(0.95 * (len(xs) - 1))], 2), "sum_s": round(sum(xs))}

    def usage_rows(path: Path, skip: int = 0) -> dict:
        """``skip``: rows copied from the recorded run when the root was cloned (the rest are this run's calls)."""
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
        rows = rows[skip:]
        return {"calls": len(rows), "input": sum(r["input"] for r in rows), "output": sum(r["output"] for r in rows),
                **lat([r["seconds"] for r in rows if r.get("seconds") is not None])}

    def journal_rows(path: Path) -> dict:
        n = inp = out = 0
        for line in path.read_text().splitlines() if path.exists() else []:
            if not line.strip():
                continue
            r = json.loads(line)
            o = count_tokens(r.get("response") or "")
            n, out, inp = n + 1, out + o, inp + max(0, int(r.get("tokens") or 0) - o)
        return {"calls": n, "input": inp, "output": out}

    wall = {}
    if STATUS_PATH.exists():
        for line in STATUS_PATH.read_text().splitlines():
            r = json.loads(line)
            if r["event"] in ("ok", "retry", "fail") and r.get("seconds"):
                wall[r["step"]] = wall.get(r["step"], 0) + r["seconds"]
    rows = []
    rec = REPO / "results" / "drift_live_ollama"
    recorded_rows = {}
    for c in ("cspaper", "player", "art", "med", "legal"):
        u = rec / c / "usage.jsonl"
        recorded_rows[c] = sum(1 for line in u.read_text().splitlines() if line.strip()) if u.exists() else 0
        rows.append({"experiment": f"recorded drift runs ({c}; builds, all streams and budgets)", **usage_rows(u)})
    for d in sorted(EXP.glob("*/live/*/usage.jsonl")):
        exp_id, c = d.parts[-4], d.parts[-2]
        if exp_id.startswith(("E2-replay", "G0-")):
            continue
        marker = d.parent / ".cloned"
        copied = marker.exists() and "usage.jsonl" in json.loads(marker.read_text()).get("copied", [])
        rows.append({"experiment": exp_id, "corpus": c, **usage_rows(d, recorded_rows.get(c, 0) if copied else 0),
                     "wall_clock_s": wall.get(exp_id)})
    v3 = REPO / "results" / "quwarts_router_v3"
    for d in sorted(v3.glob("player*/shared_read_protocol/reads.jsonl")):
        tag = d.parts[-3]
        step = {"player": None, "player_ollama": None, "player_ollama_fp16": "E1.2-sr-fp16", "player_ollama_rep1": "E1.1-sr-rep1",
                "player_ollama_rep2": "E1.1-sr-rep2", "player_ollama_nullable": "E7-sr-nullable",
                "player_ollama_nullhint": "E7b-sr-nullhint"}.get(tag)
        rows.append({"experiment": f"shared read {tag}" + (" (OpenRouter)" if tag == "player" else ""), **journal_rows(d),
                     "wall_clock_s": wall.get(step) if step else None})
    for d in sorted((EXP / "E2.1b-width").glob("*/reads.jsonl")):
        rows.append({"experiment": f"E2.1b-width-{d.parts[-2]}", **journal_rows(d), "wall_clock_s": wall.get(f"E2.1b-width-{d.parts[-2]}")})
    sweep = REPO / "results" / "quwarts_player_budget_sweep_ollama"
    for f in sorted(sweep.glob("f*")):
        pj, ej = journal_rows(f / "probe" / "probe_journal.jsonl"), journal_rows(f / "execute" / "reads.jsonl")
        rows.append({"experiment": f"planner sweep player {f.name} (probes + reads)",
                     "calls": pj["calls"] + ej["calls"], "input": pj["input"] + ej["input"], "output": pj["output"] + ej["output"]})
    for d in sorted((EXP / "usage").glob("*.jsonl")):
        rows.append({"experiment": f"runner log {d.stem}", **usage_rows(d), "wall_clock_s": wall.get(d.stem)})
    for c in ("cspaper", "player", "art", "med", "legal"):
        f = REPO / "results" / "docetl_drift_ollama" / c / "per_query.json"
        if f.exists():
            q = json.loads(f.read_text())
            rows.append({"experiment": f"DocETL drift ({c}, {len(q)} queries so far)", "calls": sum(v.get("calls", 0) for v in q.values()),
                         "input": sum(v.get("prompt_tokens", 0) for v in q.values()),
                         "output": sum(v.get("completion_tokens", 0) for v in q.values()),
                         "per_query_mean_s": round(sum(v.get("seconds", 0) for v in q.values()) / max(1, len(q)), 1),
                         "sum_s": round(sum(v.get("seconds", 0) for v in q.values()))})
    total = {"calls": sum(r.get("calls", 0) for r in rows), "input": sum(r.get("input", 0) for r in rows),
             "output": sum(r.get("output", 0) for r in rows)}
    out = {"rows": rows, "total": total}
    (EXP / "accounting.json").write_text(json.dumps(out, indent=1))
    fmt = lambda x: f"{x / 1e6:.2f}M" if isinstance(x, (int, float)) and x >= 1e5 else (f"{x:,}" if isinstance(x, int) else ("" if x is None else str(x)))  # noqa: E731
    lines = ["# Token and latency accounting", "",
             "Generated by `python -m quwarts.eval.exp_analysis accounting` from the run logs; see its docstring for sources.",
             "Latency per call is logged for drift streams, runner-logged steps and DocETL (per query); for journals that",
             "record only a total per call, input/output are split by re-counting the response, and the step's wall-clock",
             "time stands in for latency. Summed call time adds up per-call seconds across concurrent calls (8–16 at a time),",
             "so it exceeds wall-clock time.", "",
             "| Experiment | Calls | Input tokens | Output tokens | Latency per call (mean / p50 / p95 s) | Summed call time (s) | Step wall-clock (s) |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        name = r["experiment"] + (f" — {r['corpus']}" if r.get("corpus") else "")
        latency = (f"{r['mean_s']} / {r['p50_s']} / {r['p95_s']}" if "mean_s" in r else
                   (f"{r['per_query_mean_s']} per query" if "per_query_mean_s" in r else ""))
        wc, cs = r.get("wall_clock_s"), r.get("sum_s")
        lines.append(f"| {name} | {fmt(r.get('calls', 0))} | {fmt(r.get('input', 0))} | {fmt(r.get('output', 0))} | {latency} | "
                     f"{fmt(round(cs)) if cs else ''} | {fmt(round(wc)) if wc else ''} |")
    lines += ["", f"**Total:** {total['calls']:,} calls, {total['input'] / 1e6:.1f}M input tokens, {total['output'] / 1e6:.2f}M output tokens.",
              "(Recorded drift runs include every stream and budget of the recorded sweeps; experiment roots count only",
              "their new calls.)"]
    # Tokens charged per stream: what each stream would pay run alone (cached reads counted as if made), from the
    # per-query records; this is the cost the budgets and the cost charts use.
    streams_rows = []
    roots = [("recorded", REPO / "results" / "drift_live_ollama")] + [
        (d.name, d / "live") for d in sorted(EXP.glob("E*")) if (d / "live").exists() and not d.name.startswith("E2-replay")]
    for label, root in roots:
        for f in sorted(root.glob("*/streams/fixed4*-attribute_pool_*.jsonl")):
            rs = [json.loads(line) for line in f.read_text().splitlines() if line.strip()]
            import re

            m = re.fullmatch(r"fixed4(?:b(\d{3}))?-attribute_pool_(\d+)", f.stem)
            if not m:
                continue
            budget = f"{int(m.group(1))}%" if m.group(1) else "unlimited"
            streams_rows.append({"run": label, "corpus": f.parts[-3], "level": m.group(2), "budget": budget,
                                 "queries": len(rs), "patches": sum(r["action"] == "patch" for r in rs),
                                 "input": sum(r["input_tokens"] for r in rs), "output": sum(r["output_tokens"] for r in rs),
                                 "runtime_s": round(sum(r["runtime_s"] for r in rs)),
                                 "score": round(sum(r["benchmark"] for r in rs) / len(rs), 4)})
    with (EXP / "accounting_streams.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(streams_rows[0]))
        w.writeheader()
        w.writerows(streams_rows)
    lines += ["", "## Tokens charged per stream", "",
              "Every drift stream (corpus × drift level × budget, per run): tokens it would pay run alone, counting reads",
              "reused from the journal as if made (the cost the budgets and cost charts use), its patches, summed per-query",
              "runtime, and score. Build reads are charged separately (`build.json` per corpus and level). Full table:",
              "`accounting_streams.csv`.", "",
              "| Run | Corpus | Budget | Drift 0% | 25% | 50% | 75% | 100% |", "|---|---|---|---|---|---|---|---|"]
    grid: dict = {}
    for r in streams_rows:
        grid.setdefault((r["run"], r["corpus"], r["budget"]), {})[r["level"]] = r
    order = {"10%": 0, "25%": 1, "50%": 2, "75%": 3, "100%": 4, "unlimited": 5}
    for (run, corpus, budget), cells in sorted(grid.items(), key=lambda kv: (kv[0][0] != "recorded", kv[0][0], kv[0][1],
                                                                              order.get(kv[0][2], 9))):
        def cell(p):
            r = cells.get(str(p))
            return f"{(r['input'] + r['output']) / 1e6:.2f}M" if r else ""
        lines.append(f"| {run} | {corpus} | {budget} | " + " | ".join(cell(p) for p in LEVELS) + " |")
    (EXP / "ACCOUNTING.md").write_text("\n".join(lines) + "\n")
    return total


# ------------------------------------------------------------------------------------------ E5.1 planner losses

def planner_losses() -> dict:
    """E5.1: why the budgeted planner loses to one shared read on player. For each budget of the planner sweep and each
    held-out query, the score gap to the shared read (same 4-bit server) is attributed to the first cause that applies:
    a join key the query needs is (almost) empty in the planner's database; another needed column is empty; or every
    needed column was read (values differ). A column counts as empty when under 5% of its rows have a value."""

    import sqlglot
    from sqlglot import exp

    from quwarts.experiments.player_case80 import load_queries

    sql = {r["query_id"]: r["sql"] for r in load_queries()}
    shared = {r["query_id"]: r["product"] for r in json.loads(
        (REPO / "results/quwarts_router_v3/player_ollama/shared_read_protocol/score_blank.json").read_text())["read_first"]["per_query"]}
    out: dict = {}
    rows = []
    for d in sorted((REPO / "results" / "quwarts_player_budget_sweep_ollama").glob("f*")):
        score = json.loads((d / "execute" / "score.json").read_text())
        frozen = json.loads((d / "execute" / "frozen.json").read_text())["databases"]

        def fills(db: str) -> dict[tuple[str, str], float]:
            # each query is scored on its own database (its planned reads), the rest on base.db
            conn = sqlite3.connect(db)
            out_f: dict[tuple[str, str], float] = {}
            for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"):
                n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] or 1
                for c in [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')]:
                    nn = conn.execute(f'SELECT COUNT("{c}") FROM "{t}" WHERE "{c}" IS NOT NULL AND TRIM("{c}") != \'\'').fetchone()[0]
                    out_f[(t.lower(), c.lower())] = nn / n
            conn.close()
            return out_f

        cats: dict[str, list[float]] = {}
        for r in score["per_query"]:
            q = r["query_id"]
            if q not in shared or q not in sql:
                continue
            fill = fills(frozen.get(q, {}).get("db") or str(d / "execute" / "databases" / "base.db"))
            tree = sqlglot.parse_one(sql[q], read="sqlite")
            alias = {t.alias_or_name.lower(): t.name.lower() for t in tree.find_all(exp.Table)}
            tables = list(dict.fromkeys(t.name.lower() for t in tree.find_all(exp.Table)))

            def col_key(c):
                t = alias.get((c.table or "").lower()) or (tables[0] if len(tables) == 1 else None)
                if t is None:
                    t = next((tb for tb in tables if (tb, c.name.lower()) in fill), tables[0])
                return t, c.name.lower()

            join_cols = {col_key(c) for j in tree.find_all(exp.Join) for c in j.find_all(exp.Column)}
            all_cols = {col_key(c) for c in tree.find_all(exp.Column)}
            empty = lambda k: fill.get(k, 0.0) < 0.05  # noqa: E731
            if any(empty(k) for k in join_cols):
                cat = "join key empty"
            elif any(empty(k) for k in all_cols - join_cols):
                cat = "other column empty"
            else:
                cat = "all read, values differ"
            gap = shared[q] - r["product"]
            cats.setdefault(cat, []).append(gap)
            rows.append({"budget": d.name, "qid": q, "cause": cat, "planner": r["product"], "shared": shared[q],
                         "gap": round(gap, 4), "empty_columns": ";".join(f"{t}.{c}" for t, c in sorted(all_cols) if empty((t, c)))})
        out[d.name] = {"planner_mean": round(sum(x["product"] for x in score["per_query"]) / len(score["per_query"]), 4),
                       "tokens": score["total_tokens"],
                       "by_cause": {k: {"queries": len(v), "summed_gap": round(sum(v), 3), "mean_gap": round(sum(v) / len(v), 3)}
                                    for k, v in sorted(cats.items())}}
    out_dir = EXP / "E5.1-planner"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "per_query.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out_dir / "summary.json").write_text(json.dumps(out, indent=1))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["components", "patches", "order", "columns", "canon", "policies", "querytypes", "accounting", "planner", "reads", "variance"])
    ap.add_argument("--corpus")
    a = ap.parse_args(argv)
    fn = {"components": components, "patches": patches, "order": order, "columns": columns, "canon": canon, "policies": policies}.get(a.what)
    if a.what == "accounting":
        out = accounting()
    elif a.what == "planner":
        out = planner_losses()
    elif a.what == "querytypes":
        out = query_types((a.corpus or "cspaper,player,art,med,legal").split(","))
    else:
        out = fn(a.corpus) if fn else {"reads": reads, "variance": variance}[a.what]()
    print(json.dumps(out, indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["components", "patches", "order", "reads", "variance"])
    ap.add_argument("--corpus")
    a = ap.parse_args(argv)
    fn = {"components": components, "patches": patches, "order": order}.get(a.what)
    out = fn(a.corpus) if fn else {"reads": reads, "variance": variance}[a.what]()
    print(json.dumps(out, indent=1, default=str)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

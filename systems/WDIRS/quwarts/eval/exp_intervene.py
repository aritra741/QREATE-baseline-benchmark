"""I1: the context intervention on fixed documents (results/experiments/I1-context/<model>/<corpus>/reads.jsonl).

    python -m quwarts.eval.exp_intervene run --corpus cspaper --model qwen7b [--docs 30] [--workers 8] [--limit N]
    python -m quwarts.eval.exp_intervene analyze

For every new column (a column the fully drifted workload needs and the level-100 build lacks), the same sampled
documents are read under five contexts: the column alone; with two random other columns of its table; with six; in
the build's natural group (every column the level-0 build asks of the table in one prompt); and alone with a
paraphrased description. Prompts are rendered as the drift run renders them (render_prompt, the same field specs) and
sent with the same generation settings to the same servers. Resumable: a (table, document, context, focal column)
already in reads.jsonl is not asked again. Predictions (RESEARCH_DEPTH.md, I1): a column's sensitivity ranks the same
under every kind of change; average accuracy is flat across contexts but column-specific; the 32B is never more
sensitive than the 7B; on categories agreement does not predict correctness.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics as S
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router.context_probe import FieldSpec, render_prompt
from quwarts.core.router.corpus_features import read_document
from quwarts.core.router.probes import parse_fields
from quwarts.eval import drift_run as R
from quwarts.eval.exp_analysis import EXP, REPO, gold_by_doc, is_null
from quwarts.eval.exp_context import fields_of, vnorm
from quwarts.eval.exp_open import correct
from quwarts.eval.exp_transfer import kind_of
from quwarts.eval.exp_why import spearman

OUT = EXP / "I1-context"
LIVE = REPO / "results" / "drift_live_ollama"
CORPORA = ["cspaper", "player", "art", "med", "legal"]
MODELS = {"qwen7b": ("main", "qwen2.5:7b-instruct"), "qwen32b": ("qwen32b", "qwen2.5:32b-instruct"),
          "llama8b": ("llama8b", "llama3.1:8b")}
KINDS = ("alone", "plus2", "plus6", "natural", "paraphrase")
ORDER_KINDS = ("natural_shuffled", "natural_reversed")  # Q4: the natural set in another order (one order per table)
MAX_DOC_TOKENS = 9000  # every context then fits the 32B server's 16k window with room for the fields and the answer
SYSTEM = "Extract only facts stated in the document. Return JSON."  # core/llm/ollama.DEFAULT_SYSTEM
_lock = threading.Lock()


def server(name: str) -> dict:
    return json.loads((EXP / "servers" / f"{name}.json").read_text())


def chat(host: str, model: str, prompt: str, num_ctx: int, max_tokens: int = 700, temperature: float = 0.1) -> dict:
    """The drift run's request (core/llm/ollama.make_caller): same system prompt, temperature, window and answer room."""
    import httpx

    body = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "stream": False, "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": num_ctx},
            "keep_alive": "60m"}
    delay, start = 5.0, time.monotonic()
    with httpx.Client(timeout=900.0) as client:
        for attempt in range(8):
            try:
                r = client.post(f"http://{host}/api/chat", json=body)
                if r.status_code in (429, 500, 502, 503) and attempt < 7:
                    raise httpx.HTTPStatusError("retry", request=r.request, response=r)
                r.raise_for_status()
                data = r.json()
                break
            except (httpx.TransportError, httpx.HTTPStatusError):
                if attempt == 7:
                    raise
                time.sleep(delay)
                delay = min(delay * 2, 120)
    return {"response": ((data.get("message") or {}).get("content") or "").strip(),
            "prompt_tokens": int(data.get("prompt_eval_count") or 0), "output_tokens": int(data.get("eval_count") or 0),
            "seconds": round(time.monotonic() - start, 2), "cut_off": data.get("done_reason") == "length"}


def gold_row(gold_t: dict, doc: str):
    return gold_t.get(doc) or gold_t.get(doc.rsplit(".", 1)[0]) or gold_t.get(doc + ".txt")


def natural_groups(corpus: str) -> dict[str, tuple]:
    """Per table, the widest attribute set a build prompt asked of it (the level-0 build: workload and new columns)."""
    best: dict[str, tuple] = {}
    f = LIVE / corpus / "build_reads.jsonl"
    for line in f.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        t, attrs = r["table"], tuple(sorted(r["attributes"]))
        if len(attrs) > len(best.get(t, ())):
            best[t] = attrs
    return best


def paraphrases(corpus: str, fields: dict, new: list[str]) -> dict[str, str]:
    """One paraphrase per new column's description, made once by the 7B server and kept for every model."""
    path = OUT / "paraphrase" / f"{corpus}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    out = json.loads(path.read_text()) if path.exists() else {}
    srv = server("main")
    for col in new:
        if col in out:
            continue
        desc = fields[col].description or col.split(".", 1)[1].replace("_", " ")
        prompt = ("Rewrite the following description of a data field in different words. Keep exactly the same meaning, "
                  "the same examples and the same level of detail. Reply with the new description only, on one line.\n\n"
                  f"{desc}")
        r = chat(srv["host"], "qwen2.5:7b-instruct", prompt, srv["context"], max_tokens=200, temperature=0.0)
        text = r["response"].strip().strip('"').splitlines()[0].strip() if r["response"].strip() else desc
        out[col] = text if 0.3 * len(desc) <= len(text) <= 3 * len(desc) + 40 else desc
        path.write_text(json.dumps(out, indent=1))
    return out


def sample_docs(corpus: str, ctx, table: str, gold_t: dict, n: int) -> list[str]:
    rng = random.Random(f"{corpus}:{table}:I1")
    ok = []
    for d, p in ctx.docs[table].items():
        if gold_row(gold_t, d) is None:
            continue
        if count_tokens(read_document(Path(p))) <= MAX_DOC_TOKENS:
            ok.append(d)
    ok.sort()
    rng.shuffle(ok)
    return ok[:n]


def plan(corpus: str, n_docs: int) -> list[dict]:
    """Every prompt to send: (table, doc, kind, focal column, attributes), the natural group once per (table, doc)."""
    ctx = R.context(corpus)
    fields = fields_of(corpus)
    design = json.loads((LIVE / corpus / "fixed4_attribute_pool_design.json").read_text())
    new = [c for c in design["new_columns"] if c in fields]
    gold = gold_by_doc(corpus)
    natural = natural_groups(corpus)
    para = paraphrases(corpus, fields, new)
    by_table = defaultdict(list)
    for col in new:
        by_table[col.split(".", 1)[0]].append(col)
    jobs = []
    for t, cols in by_table.items():
        docs = sample_docs(corpus, ctx, t, gold.get(t, {}), n_docs)
        others_all = sorted(k.split(".", 1)[1] for k in fields if k.startswith(t + "."))
        nat0 = natural.get(t) or tuple(sorted({c.split(".", 1)[1] for c in cols}))
        shuffled = list(nat0)
        random.Random(f"{corpus}:{t}:order").shuffle(shuffled)
        if shuffled == list(nat0) and len(shuffled) > 1:
            shuffled = shuffled[1:] + shuffled[:1]
        for d in docs:
            nat = nat0
            jobs.append({"table": t, "doc": d, "kind": "natural", "focal": None, "attributes": list(nat)})
            jobs.append({"table": t, "doc": d, "kind": "natural_shuffled", "focal": None, "attributes": shuffled})
            jobs.append({"table": t, "doc": d, "kind": "natural_reversed", "focal": None, "attributes": list(reversed(nat))})
            for col in cols:
                a = col.split(".", 1)[1]
                rng = random.Random(f"{corpus}:{col}:I1")
                others = [x for x in others_all if x != a]
                plus2 = sorted([a] + rng.sample(others, min(2, len(others))))
                plus6 = sorted([a] + rng.sample(others, min(6, len(others))))
                jobs.append({"table": t, "doc": d, "kind": "alone", "focal": a, "attributes": [a]})
                jobs.append({"table": t, "doc": d, "kind": "plus2", "focal": a, "attributes": plus2})
                jobs.append({"table": t, "doc": d, "kind": "plus6", "focal": a, "attributes": plus6})
                jobs.append({"table": t, "doc": d, "kind": "paraphrase", "focal": a, "attributes": [a],
                             "description": para.get(col)})
    return jobs


def key_of(j: dict) -> str:
    return f"{j['table']}|{j['doc']}|{j['kind']}|{j['focal'] or ''}"


def run(corpus: str, model: str, n_docs: int, workers: int, limit: int | None) -> None:
    srv_name, model_name = MODELS[model]
    srv = server(srv_name)
    ctx = R.context(corpus)
    fields = fields_of(corpus)
    out = OUT / model / corpus
    out.mkdir(parents=True, exist_ok=True)
    journal = out / "reads.jsonl"
    done = set()
    if journal.exists():
        for line in journal.read_text().splitlines():
            if line.strip():
                done.add(key_of(json.loads(line)))
    jobs = [j for j in plan(corpus, n_docs) if key_of(j) not in done]
    if limit:
        jobs = jobs[:limit]
    print(f"{corpus} {model}: {len(jobs)} prompts to send ({len(done)} done)", flush=True)
    texts: dict[str, str] = {}

    def text_of(t: str, d: str) -> str:
        k = f"{t}|{d}"
        if k not in texts:
            texts[k] = read_document(Path(ctx.docs[t][d]))
        return texts[k]

    def one(j: dict) -> None:
        t = j["table"]
        specs = []
        for a in j["attributes"]:
            f = fields[f"{t}.{a}"]
            if j["kind"] == "paraphrase" and j.get("description"):
                f = replace(f, description=j["description"])
            specs.append(f)
        prompt = render_prompt(text_of(t, j["doc"]), specs, None)
        r = chat(srv["host"], model_name, prompt, srv["context"])
        row = {**j, "model": model_name, "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:16],
               "prompt_count": count_tokens(prompt), **r}
        with _lock:
            with journal.open("a") as h:
                h.write(json.dumps(row) + "\n")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, _ in enumerate(ex.map(one, jobs), 1):
            if i % 200 == 0:
                print(f"  {i}/{len(jobs)}  {(time.time() - t0) / 60:.1f} min", flush=True)
    print(f"{corpus} {model}: done in {(time.time() - t0) / 60:.1f} min", flush=True)


# ------------------------------------------------------------------ analysis

def analyze() -> dict:
    out = {"per_model": {}, "across_models": {}}
    cols_by_model: dict[str, dict] = {}
    for model in MODELS:
        rows = []
        for c in CORPORA:
            j = OUT / model / c / "reads.jsonl"
            if not j.exists():
                continue
            fields = fields_of(c)
            gold = gold_by_doc(c)
            design = json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())
            new = {x.split(".", 1)[1] for x in design["new_columns"]}
            vals: dict[tuple, dict[str, object]] = defaultdict(dict)  # (t, d, a) -> kind -> value
            for line in j.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                parsed = parse_fields(r["response"], r["attributes"])
                for a in r["attributes"]:
                    if r["kind"] in ("natural",) + ORDER_KINDS and a not in new:
                        continue
                    if r["focal"] is None or r["focal"] == a:
                        vals[(r["table"], r["doc"], a)][r["kind"]] = parsed.get(a)
            per_col: dict[str, list] = defaultdict(list)
            for (t, d, a), kinds in vals.items():
                g = gold_row(gold.get(t, {}), d)
                if g is None or a not in g:
                    continue
                per_col[f"{t}.{a}"].append((kinds, g[a]))
            for col, items in per_col.items():
                if len(items) < 10 or col not in fields:
                    continue
                e = {"corpus": c, "column": col, "kind": kind_of(fields[col]), "docs": len(items), "accuracy": {},
                     "empty": {}, "sensitivity": {}}
                for k in KINDS:
                    have = [(kinds[k], g) for kinds, g in items if k in kinds]
                    if have:
                        e["accuracy"][k] = round(S.mean(correct(v, g) for v, g in have), 3)
                        e["empty"][k] = round(S.mean(is_null(v) for v, _ in have), 3)
                for k in KINDS[1:]:
                    both = [(kinds["alone"], kinds[k]) for kinds, _ in items if "alone" in kinds and k in kinds]
                    if len(both) >= 10:
                        e["sensitivity"][k] = round(S.mean(vnorm(x) != vnorm(y) for x, y in both), 3)
                if len(e["sensitivity"]) >= 2:
                    e["mean_sensitivity"] = round(S.mean(e["sensitivity"].values()), 3)
                # agreement vs correctness of the lone answer (the category test)
                agree = [(kinds["alone"], g) for kinds, g in items if "alone" in kinds and "natural" in kinds
                         and vnorm(kinds["alone"]) == vnorm(kinds["natural"])]
                differ = [(kinds["alone"], g) for kinds, g in items if "alone" in kinds and "natural" in kinds
                          and vnorm(kinds["alone"]) != vnorm(kinds["natural"])]
                for ok in ORDER_KINDS:  # Q4: same set, another order
                    both = [(kinds["natural"], kinds[ok]) for kinds, _ in items if "natural" in kinds and ok in kinds]
                    if len(both) >= 10:
                        e["order_change_" + ok.split("_")[1]] = round(S.mean(vnorm(x) != vnorm(y) for x, y in both), 3)
                        have = [(kinds[ok], g) for kinds, g in items if ok in kinds]
                        e["accuracy"][ok] = round(S.mean(correct(v, g) for v, g in have), 3)
                e["accuracy_when_agree"] = round(S.mean(correct(v, g) for v, g in agree), 3) if agree else None
                e["accuracy_when_differ"] = round(S.mean(correct(v, g) for v, g in differ), 3) if differ else None
                e["n_agree"], e["n_differ"] = len(agree), len(differ)
                rows.append(e)
        if not rows:
            continue
        cols_by_model[model] = {(r["corpus"], r["column"]): r for r in rows}
        m = {"columns": len(rows)}
        # (a) does the column ranking hold across kinds of change?
        pairs = {}
        for k1 in KINDS[1:]:
            for k2 in KINDS[1:]:
                if k1 < k2:
                    rs = [r for r in rows if k1 in r["sensitivity"] and k2 in r["sensitivity"]]
                    if len(rs) >= 5:
                        pairs[f"{k1}_vs_{k2}"] = {"columns": len(rs), "spearman": round(spearman(
                            [r["sensitivity"][k1] for r in rs], [r["sensitivity"][k2] for r in rs]), 3)}
        m["sensitivity_rank_across_kinds_of_change"] = pairs
        # (b) sensitivity vs accuracy; accuracy flat across contexts on average, column-specific in direction
        rs = [r for r in rows if "mean_sensitivity" in r and "alone" in r["accuracy"]]
        m["spearman_mean_sensitivity_vs_accuracy_alone"] = round(spearman(
            [r["mean_sensitivity"] for r in rs], [r["accuracy"]["alone"] for r in rs]), 3) if len(rs) > 4 else None
        m["mean_accuracy_by_context"] = {k: round(S.mean(r["accuracy"][k] for r in rows if k in r["accuracy"]), 3)
                                         for k in KINDS if any(k in r["accuracy"] for r in rows)}
        m["mean_empty_by_context"] = {k: round(S.mean(r["empty"][k] for r in rows if k in r["empty"]), 3)
                                      for k in KINDS if any(k in r["empty"] for r in rows)}
        m["columns_better_alone_than_natural"] = sum(r["accuracy"].get("alone", 0) > r["accuracy"].get("natural", 0) + 0.05 for r in rows)
        m["columns_better_natural_than_alone"] = sum(r["accuracy"].get("natural", 0) > r["accuracy"].get("alone", 0) + 0.05 for r in rows)
        # Q4 summary: order-only changes against set changes
        oc = [r for r in rows if "order_change_shuffled" in r and "natural" in r["sensitivity"]]
        if oc:
            m["order_effect"] = {"columns": len(oc),
                                 "mean_change_shuffled": round(S.mean(r["order_change_shuffled"] for r in oc), 3),
                                 "mean_change_reversed": round(S.mean(r.get("order_change_reversed", r["order_change_shuffled"]) for r in oc), 3),
                                 "mean_change_set_plus6_vs_alone": round(S.mean(r["sensitivity"]["plus6"] for r in oc if "plus6" in r["sensitivity"]), 3),
                                 "spearman_order_change_vs_sensitivity": round(spearman([r["order_change_shuffled"] for r in oc], [r["mean_sensitivity"] for r in oc if "mean_sensitivity" in r]), 3) if all("mean_sensitivity" in r for r in oc) and len(oc) > 4 else None,
                                 "accuracy_natural": round(S.mean(r["accuracy"]["natural"] for r in oc), 3),
                                 "accuracy_shuffled": round(S.mean(r["accuracy"]["natural_shuffled"] for r in oc), 3),
                                 "columns_changing_over_0.2": sum(r["order_change_shuffled"] > 0.2 for r in oc),
                                 "by_kind": {k: round(S.mean(r["order_change_shuffled"] for r in oc if r["kind"] == k), 3)
                                             for k in ("number", "yes/no", "category", "list", "free text") if any(r["kind"] == k for r in oc)}}
        m["mean_sensitivity_by_kind"] = {}
        for k in ("number", "yes/no", "category", "list", "free text"):
            rs = [r for r in rows if r["kind"] == k and "mean_sensitivity" in r]
            if rs:
                m["mean_sensitivity_by_kind"][k] = {"columns": len(rs), "sensitivity": round(S.mean(r["mean_sensitivity"] for r in rs), 3),
                                                    "accuracy_alone": round(S.mean(r["accuracy"].get("alone", 0) for r in rs), 3)}
        # (d) the category test: pooled over cells
        m["agreement_vs_correctness"] = {}
        for k in ("all", "number", "yes/no", "category", "list", "free text"):
            rs = [r for r in rows if (k == "all" or r["kind"] == k) and r["accuracy_when_agree"] is not None and r["accuracy_when_differ"] is not None]
            if rs:
                na, nd = sum(r["n_agree"] for r in rs), sum(r["n_differ"] for r in rs)
                m["agreement_vs_correctness"][k] = {
                    "columns": len(rs), "cells_agree": na, "cells_differ": nd,
                    "accuracy_when_agree": round(sum(r["accuracy_when_agree"] * r["n_agree"] for r in rs) / na, 3),
                    "accuracy_when_differ": round(sum(r["accuracy_when_differ"] * r["n_differ"] for r in rs) / nd, 3)}
        out["per_model"][model] = m
    # (c) the 32B against the 7B, column by column
    for a, b in (("qwen7b", "qwen32b"), ("qwen7b", "llama8b")):
        if a in cols_by_model and b in cols_by_model:
            shared = [k for k in cols_by_model[a] if k in cols_by_model[b]
                      and "mean_sensitivity" in cols_by_model[a][k] and "mean_sensitivity" in cols_by_model[b][k]]
            if len(shared) >= 5:
                sa = [cols_by_model[a][k]["mean_sensitivity"] for k in shared]
                sb = [cols_by_model[b][k]["mean_sensitivity"] for k in shared]
                out["across_models"][f"{a}_vs_{b}"] = {
                    "shared_columns": len(shared), "spearman_sensitivity": round(spearman(sa, sb), 3),
                    f"mean_sensitivity_{a}": round(S.mean(sa), 3), f"mean_sensitivity_{b}": round(S.mean(sb), 3),
                    f"columns_where_{b}_more_sensitive_by_0.05": sum(y > x + 0.05 for x, y in zip(sa, sb)),
                    f"spearman_{a}_sensitivity_vs_{b}_accuracy_alone": round(spearman(
                        sa, [cols_by_model[b][k]["accuracy"].get("alone", 0) for k in shared]), 3)}
    out["columns"] = {m: list(v.values()) for m, v in cols_by_model.items()}
    (OUT / "summary.json").write_text(json.dumps(out, indent=1, default=str))
    return out




# ------------------------------------------------------------------ I5 groupings

def write_groupings(kind: str) -> list[Path]:
    """I5: build-time groupings of the new columns per corpus (results/experiments/I5-groups/<corpus>_<kind>.json):
    ``alone`` gives every new column its own prompt; ``chosen`` separates the columns that I1 found more accurate
    alone than in the natural group (by 0.05 on the sampled documents) and keeps the rest together."""
    d = EXP / "I5-groups"
    d.mkdir(parents=True, exist_ok=True)
    summary = json.loads((OUT / "summary.json").read_text()) if kind == "chosen" else {}
    acc = {(r["corpus"], r["column"]): r["accuracy"] for r in summary.get("columns", {}).get("qwen7b", [])}
    out = []
    for c in CORPORA:
        design = json.loads((LIVE / c / "fixed4_attribute_pool_design.json").read_text())
        by_table = defaultdict(list)
        for col in design["new_columns"]:
            by_table[col.split(".", 1)[0]].append(col.split(".", 1)[1])
        groups = {}
        for t, cols in by_table.items():
            if kind == "alone":
                groups[t] = [[a] for a in cols]
            else:
                alone = [a for a in cols if acc.get((c, f"{t}.{a}"), {}).get("alone", 0) >= acc.get((c, f"{t}.{a}"), {}).get("natural", 0) + 0.05]
                rest = [a for a in cols if a not in alone]
                groups[t] = [[a] for a in alone] + ([rest] if rest else [])
        p = d / f"{c}_{kind}.json"
        p.write_text(json.dumps(groups, indent=1))
        out.append(p)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["run", "analyze", "plan", "groups"])
    ap.add_argument("--kind", default="alone", choices=["alone", "chosen"])
    ap.add_argument("--corpus")
    ap.add_argument("--model", default="qwen7b", choices=list(MODELS))
    ap.add_argument("--docs", type=int, default=30)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)
    if a.what == "run":
        run(a.corpus, a.model, a.docs, a.workers, a.limit)
    elif a.what == "groups":
        print([str(p) for p in write_groupings(a.kind)])
    elif a.what == "plan":
        jobs = plan(a.corpus, a.docs)
        print(len(jobs), "prompts;", Counter(j["kind"] for j in jobs))
    else:
        o = analyze()
        print(json.dumps({k: v for k, v in o.items() if k != "columns"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

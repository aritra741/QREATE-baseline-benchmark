"""Which gold-free signal ranks providers the way gold does? (development corpora only)

The router must choose, per need, among providers (reads) without gold. Router-v3
scored every provider against the need's own query-context read, which silently
assumes that read is correct. This experiment tests that assumption and two
alternatives on a document sample, then compares each signal's choices with gold.

Reads per sampled document (Qwen 2.5 7B, whole document within the operator window):
  canonical x2   all needed attributes, no query context
  evidence x1    all needed attributes, each with a verbatim supporting quote; a value
                 whose quote is not found in the document is treated as unsupported (null)
  own(q) x1      per workload query: that query's attributes with its SQL as context

Gold-free signals, for need i and provider p:
  own        agreement with i's own query-context read (router-v3.0)
  consensus  agreement with the leave-one-out plurality of every other read of the
             attribute on that document (benchmark equivalence)
  evidence   agreement with the evidence-grounded read

For each signal: per-need rank correlation with gold over providers, the gold regret of
the provider it would pick, and the gold score of the resulting per-need choice. Gold is
read only by ``--score``, after all outputs are stored.

    python -m quwarts.eval.router_reference_validation --corpus cspaper --docs 30 --run
    python -m quwarts.eval.router_reference_validation --corpus cspaper --docs 30 --score
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
from collections import Counter, defaultdict
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router.comparator import as_text, is_null, need_score
from quwarts.core.router.context_probe import SYSTEM, V3, FieldSpec, complete, conform, field_specs, render_prompt, truncate
from quwarts.core.router.corpus_features import length_stratified_sample, list_documents, read_document
from quwarts.core.router.needs import CANONICAL, Need, workload_needs
from quwarts.core.router.probes import parse_fields
from quwarts.core.router.registry import PROJECT, RESULTS, get_corpus
from quwarts.core.router.text import prepare_document
from quwarts.core.router.workload_features import workload_features

EVIDENCE = "__evidence__"
WORKLOAD = "__workload__"  # all fields, no SQL, each described by its workload use
SUBSET = "__subset__"  # prefix: the query's own field subset, read without SQL context
DATASET = {"finan": "Finan", "legal": "Legal", "med": "Med", "cspaper": "CSPaper", "art": "Art", "player": "Player"}
_lock = threading.Lock()


def evidence_prompt(document: str, fields: list[FieldSpec]) -> str:
    lines = "\n".join(f.line() for f in fields)
    return (
        "Extract the following fields about the single entity described in the document.\n"
        "For every field give the value and a short verbatim quote from the document that supports it.\n"
        "Use null for both when the document does not support a value.\n\n"
        f"DOCUMENT:\n{document}\n\nFIELDS:\n{lines}\n\n"
        'Return JSON with this shape and no other keys: '
        '{"fields": {"<field>": {"value": <value or null>, "evidence": "<quote or null>"}}}'
    )


def supported(item: Any, document_lower: str) -> Any:
    if not isinstance(item, dict):
        return None
    value, quote = item.get("value"), item.get("evidence")
    if is_null(value) or not isinstance(quote, str) or len(quote.strip()) < 3:
        return None
    return value if prepare_document(quote).strip(" .\"'") in document_lower else None


def setup(corpus: str, k: int):
    spec = get_corpus(corpus)
    queries = spec.queries()
    needs = workload_needs(spec, queries)
    numeric = {q for q, u in workload_features(spec, queries)["attributes"].items() if u.numeric}
    fields = field_specs(spec, needs, numeric)
    tables = sorted({n.table for n in needs})
    docs = {}
    for table in tables:
        paths = list_documents(spec.table(table))
        tokens = {p.name: len(p.read_bytes()) for p in paths}
        docs[table] = length_stratified_sample(paths, tokens, k, f"refval:{table}")
    return spec, queries, needs, fields, docs


def tasks_for(spec, queries, needs, fields, docs, subsets: bool = False,
              usage: dict[str, str] | None = None) -> list[dict[str, Any]]:
    window = int(V3["window_tokens"])
    tasks = []
    for table, paths in docs.items():
        attrs = sorted({n.attribute for n in needs if n.table == table})
        specs = [fields[f"{table}.{a}"] for a in attrs]
        contexts = sorted({n.query_id for n in needs if n.table == table})
        for path in paths:
            text = truncate(read_document(path), window)
            base = {"table": table, "doc": path.name}
            for rep in (1, 2):
                tasks.append({**base, "kind": CANONICAL, "rep": rep, "attributes": attrs,
                              "prompt": render_prompt(text, specs, None) + ("" if rep == 1 else " ")})
            tasks.append({**base, "kind": EVIDENCE, "rep": 1, "attributes": attrs, "prompt": evidence_prompt(text, specs)})
            if usage:
                w_specs = [replace(fields[f"{table}.{a}"], usage=usage.get(f"{table}.{a}", "")) for a in attrs]
                tasks.append({**base, "kind": WORKLOAD, "rep": 1, "attributes": attrs, "prompt": render_prompt(text, w_specs, None)})
            for q in contexts:
                q_attrs = sorted({n.attribute for n in needs if n.table == table and n.query_id == q})
                q_specs = [fields[f"{table}.{a}"] for a in q_attrs]
                tasks.append({**base, "kind": q, "rep": 1, "attributes": q_attrs,
                              "prompt": render_prompt(text, q_specs, queries[q])})
                if subsets:
                    tasks.append({**base, "kind": SUBSET + q, "rep": 1, "attributes": q_attrs,
                                  "prompt": render_prompt(text, q_specs, None)})
    for t in tasks:
        t["sha"] = hashlib.sha256(t["prompt"].encode()).hexdigest()
    return tasks


def run(out: Path, tasks: list[dict[str, Any]], workers: int) -> None:
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.llm.openrouter import load_env_file, make_caller

    out.mkdir(parents=True, exist_ok=True)
    journal = out / "calls.jsonl"
    done = {json.loads(l)["sha"] for l in journal.read_text().splitlines()} if journal.exists() else set()
    todo = [t for t in tasks if t["sha"] not in done]
    load_env_file(PROJECT / ".env")
    ledger = TokenLedger(theta=10**12)
    caller = make_caller(ledger, max_tokens=500)

    def one(task):
        text = caller.complete(task["prompt"], "reference_validation", system=SYSTEM)
        row = {k: v for k, v in task.items() if k != "prompt"}
        row.update(response=text, tokens=ledger.records[-1].tokens, prompt_tokens=count_tokens(task["prompt"]))
        with _lock, journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))


def load_reads(out: Path, docs, fields: dict[str, FieldSpec] | None = None,
               completion: bool = False) -> dict[tuple[str, str], dict[str, Any]]:
    """reads[(table, doc)][provider] = {attribute: value}; canonical rep 2 stored as '__canonical__#2'."""

    lowered = {(t, p.name): prepare_document(read_document(p)) for t, ps in docs.items() for p in ps}
    reads: dict[tuple[str, str], dict[str, Any]] = defaultdict(dict)
    for line in (out / "calls.jsonl").read_text().splitlines():
        row = json.loads(line)
        parsed = parse_fields(row["response"], row["attributes"])
        key = (row["table"], row["doc"])
        if row["kind"] == EVIDENCE:
            vals = {a: supported(parsed.get(a), lowered[key]) for a in row["attributes"]}
        else:
            vals = {a: parsed.get(a) for a in row["attributes"]}
        if fields is not None:
            fix = complete if completion else conform
            vals = {a: fix(v, fields[f"{row['table']}.{a}"]) for a, v in vals.items()}
        name = row["kind"] if row["rep"] == 1 else f"{row['kind']}#2"
        reads[key][name] = vals
    return reads


def plurality(values: list[Any], need: Need, value_type: str) -> Any:
    """The value most others agree with (benchmark equivalence for this need)."""

    if not values:
        return None
    best, best_score = None, -1.0
    for candidate in values:
        score = sum(need_score(need, candidate, other, value_type) for other in values)
        if score > best_score + 1e-9:
            best, best_score = candidate, score
    return best


def kendall(a: list[float], b: list[float]) -> float | None:
    pairs = conc = disc = 0
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            x, y = a[i] - a[j], b[i] - b[j]
            if x == 0 or y == 0:
                continue
            pairs += 1
            conc += (x > 0) == (y > 0)
            disc += (x > 0) != (y > 0)
    return None if pairs == 0 else (conc - disc) / pairs


def score(corpus: str, out: Path, needs, fields, docs, completion: bool = False) -> dict[str, Any]:
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.experiments.synthesize_case80 import gold_name

    reads = load_reads(out, docs, fields, completion)
    gold_tables = load_ground_truth(gold_name(DATASET[corpus]))  # gold read only here

    def gold_row(table: str, doc: str) -> dict[str, Any]:
        rows = gold_tables.get(table) or next(iter(gold_tables.values()))
        stem = Path(doc).stem

        def same(a: str, b: str) -> bool:
            return a == b or (a.isdigit() and b.isdigit() and int(a) == int(b))  # Art ids are zero-padded

        for r in rows:
            for key in ("pdf_filename", "doc_id", "id", "file", "filename"):
                if key in r and same(Path(str(r[key])).stem, stem):
                    return r
        return {}

    by_attr: dict[str, list[Need]] = defaultdict(list)
    for n in needs:
        by_attr[n.qualified].append(n)
    signals = ["own", "consensus", "evidence"]
    per_need = []
    for need in needs:
        vt = fields[need.qualified].value_type
        contexts = sorted({m.query_id for m in by_attr[need.qualified]})
        providers = [CANONICAL, EVIDENCE, WORKLOAD] + contexts + [SUBSET + q for q in contexts]
        gold_s: dict[str, list[float]] = defaultdict(list)
        sig_s: dict[str, dict[str, list[float]]] = {s: defaultdict(list) for s in signals}
        for (table, doc), ctx in reads.items():
            if table != need.table or need.query_id not in ctx:
                continue
            g = gold_row(table, doc).get(need.attribute.lower())
            own = ctx[need.query_id].get(need.attribute)
            evid = ctx.get(EVIDENCE, {}).get(need.attribute)
            all_reads = {name: vals[need.attribute] for name, vals in ctx.items() if need.attribute in vals}
            for p in providers:
                if p not in ctx or need.attribute not in ctx[p]:
                    continue
                v = ctx[p][need.attribute]
                gold_s[p].append(need_score(need, v, g, vt))
                sig_s["own"][p].append(need_score(need, v, own, vt))
                others = [x for name, x in all_reads.items() if name != p]
                sig_s["consensus"][p].append(need_score(need, v, plurality(others, need, vt), vt))
                sig_s["evidence"][p].append(need_score(need, v, evid, vt))
        mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
        ps = [p for p in providers if gold_s[p]]
        gold_mean = {p: mean(gold_s[p]) for p in ps}
        row = {"need": need.key, "kind": need.kind, "weight": need.weight, "gold": gold_mean,
               "best_gold": max(gold_mean.values()) if gold_mean else None}
        for s in signals:
            sm = {p: mean(sig_s[s][p]) for p in ps}
            # Exclude the reference itself from the choice it would trivially win.
            eligible = [p for p in ps if not (s == "own" and p == need.query_id) and not (s == "evidence" and p == EVIDENCE)]
            pick = max(eligible, key=lambda p: (sm[p], p == CANONICAL)) if eligible else None
            row[s] = {
                "tau": kendall([gold_mean[p] for p in ps], [sm[p] for p in ps]) if len(ps) > 2 else None,
                "pick": pick,
                "pick_gold": gold_mean.get(pick) if pick else None,
            }
        per_need.append(row)

    total_w = sum(r["weight"] for r in per_need)
    summary = {}
    for s in signals:
        taus = [r[s]["tau"] for r in per_need if r[s]["tau"] is not None]
        summary[s] = {
            "mean_tau": sum(taus) / len(taus) if taus else None,
            "weighted_gold_of_picks": sum(r["weight"] * (r[s]["pick_gold"] or 0) for r in per_need) / total_w,
        }
    summary["oracle"] = {"weighted_gold_of_picks": sum(r["weight"] * (r["best_gold"] or 0) for r in per_need) / total_w}
    for fixed in (CANONICAL, EVIDENCE, WORKLOAD, "own", "own_subset"):
        if fixed == "own":
            key = lambda r: r["need"].split("|")[0]  # noqa: E731
        elif fixed == "own_subset":
            key = lambda r: SUBSET + r["need"].split("|")[0]  # noqa: E731
        else:
            key = lambda r, f=fixed: f  # noqa: E731
        summary[f"always_{fixed.strip('_')}"] = {
            "weighted_gold_of_picks": sum(r["weight"] * (r["gold"].get(key(r)) or 0) for r in per_need) / total_w}
    tokens = defaultdict(list)
    for line in (out / "calls.jsonl").read_text().splitlines():
        row = json.loads(line)
        kind = row["kind"]
        tokens["canonical" if kind == CANONICAL else "evidence" if kind == EVIDENCE else "workload" if kind == WORKLOAD
               else "subset" if kind.startswith(SUBSET) else "query"].append(row["tokens"])
    summary["tokens_per_call"] = {k: sum(v) / len(v) for k, v in tokens.items()}
    return {"summary": summary, "per_need": per_need}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--docs", type=int, default=30)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--tag", default="", help="output subfolder suffix, e.g. 'contract'")
    parser.add_argument("--subsets", action="store_true", help="also read each query's field subset without SQL")
    parser.add_argument("--workload", action="store_true", help="also run the workload-informed shared read")
    parser.add_argument("--completion", action="store_true", help="score with declared absence values applied")
    args = parser.parse_args()
    out = RESULTS / "quwarts_router_v3" / "reference_validation" / (args.corpus + (f"_{args.tag}" if args.tag else ""))
    spec, queries, needs, fields, docs = setup(args.corpus, args.docs)
    if args.run:
        usage = None
        if args.workload:
            from quwarts.core.router.workload_features import usage_phrase, workload_features

            usage = {q: usage_phrase(u) for q, u in workload_features(spec, queries)["attributes"].items()}
        tasks = tasks_for(spec, queries, needs, fields, docs, subsets=args.subsets, usage=usage)
        print(f"{len(tasks)} calls, ~{sum(count_tokens(t['prompt']) + 150 for t in tasks):,} tokens", flush=True)
        run(out, tasks, args.workers)
    if args.score:
        report = score(args.corpus, out, needs, fields, docs, args.completion)
        (out / ("report_completion.json" if args.completion else "report.json")).write_text(json.dumps(report, indent=2, default=str))
        print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()

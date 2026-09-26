"""Diagnostic: which read strategy works best on long documents (Finan, a development corpus).

Strategies, all with Qwen 2.5 7B and the same field prompt (no query context):

* ``head``        the first 10,108 tokens of the filing, one call (DocETL-style truncation)
* ``window_1``    one call over a 10,108-token window assembled from each attribute's top BM25
                  chunks (round-robin), i.e. attribute-targeted chunking with one shared read
* ``window_small`` as window_1 but 2,900 tokens: the largest bundled read that fits theta25
* ``window_attr`` one call per attribute over its own top BM25 chunks (up to 3,000 tokens)
* ``exhaustive``  every 3,000-token chunk, one call each, majority of non-null answers per
                  attribute (the expensive full-coverage reference)
* ``program``     the stored official Finan program-synthesis database (no new calls)
* ``plumbing``    the stored plumbing database (no new calls)

Reported per strategy: tokens per document; cell score against gold (benchmark rules,
plus a 1% relative-error variant for numbers); agreement with ``exhaustive`` (the gold-free
signal a router could use); and window recall (is the gold value's text inside what the
model saw). Gold is read only in the scoring step, after all model outputs are stored.
This is a development diagnostic, not a frozen result.

    python -m quwarts.eval.router_long_doc_experiment --docs 20 --run     # model calls (resumable)
    python -m quwarts.eval.router_long_doc_experiment --docs 20 --score   # zero-token scoring
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from quwarts.core.corpus_probe.context import exhaustive_chunks
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router.comparator import as_text, is_null, value_score
from quwarts.core.router.context_probe import FieldSpec, render_prompt, truncate
from quwarts.core.router.corpus_features import length_stratified_sample, list_documents, read_document
from quwarts.core.router.needs import workload_needs
from quwarts.core.router.probes import parse_fields
from quwarts.core.router.registry import PROJECT, RESULTS, get_corpus
from quwarts.core.router.text import find_span, prepare_document

OUT = RESULTS / "quwarts_router_v3" / "finan_long_doc"
WINDOW = 10_108
ATTR_WINDOW = 3_000
SMALL_WINDOW = 2_900  # one bundled read that fits theta25 on Finan (~3.5k tokens per filing)
CHUNK = 600
EXHAUSTIVE_CHUNK = 3_000
OVERHEAD = 600
SYSTEM = "Extract only facts stated in the document. Return JSON."
_STOP = {"the", "and", "for", "with", "from", "that", "this", "enter", "number", "original", "currency",
         "convert", "usd", "using", "rate", "period", "reporting", "choose", "one", "more", "only", "unit"}
_lock = threading.Lock()


# ---------------------------------------------------------------- inputs
def attributes(spec) -> list[FieldSpec]:
    descriptions = {k.lower(): v for k, v in spec.descriptions()["finance"].items()}
    names = sorted({n.attribute for n in workload_needs(spec)})
    return [FieldSpec(name, str(descriptions.get(name.lower(), {}).get("value_type", "str")),
                      str(descriptions.get(name.lower(), {}).get("description", ""))) for name in names]


def sample_docs(spec, k: int) -> list[Path]:
    table = spec.table("finance")
    paths = list_documents(table)
    tokens = {p.name: len(p.read_bytes()) for p in paths}  # byte length is enough to stratify
    return length_stratified_sample(paths, tokens, k, "long-doc-experiment")


# ---------------------------------------------------------------- retrieval
def _terms(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP]


def bm25_rank(chunks: list[dict], query: list[str], k1: float = 1.5, b: float = 0.75) -> list[int]:
    docs = [_terms(c["text"]) for c in chunks]
    n = len(docs)
    avg = sum(len(d) for d in docs) / max(1, n)
    df = Counter(t for d in docs for t in set(d))
    scores = []
    for i, d in enumerate(docs):
        tf = Counter(d)
        s = 0.0
        for t in set(query):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * len(d) / max(1, avg)))
        scores.append((s, -i))
    return [-neg for _s, neg in sorted(scores, reverse=True)]


def attr_query(field: FieldSpec) -> list[str]:
    return _terms(field.name.replace("_", " ") + " " + field.description) + _terms(field.name.replace("_", " ")) * 2


def assemble(chunks: list[dict], order: list[int], budget: int) -> str:
    chosen, used = [], 0
    for i in order:
        if used + chunks[i]["tokens"] > budget:
            continue
        chosen.append(i)
        used += chunks[i]["tokens"]
    return "\n...\n".join(chunks[i]["text"] for i in sorted(chosen))


def window_one(text: str, fields: list[FieldSpec], budget: int = WINDOW) -> str:
    chunks = exhaustive_chunks(text, CHUNK)
    ranks = [bm25_rank(chunks, attr_query(f)) for f in fields]
    order, seen = [], set()
    for depth in range(len(chunks)):
        for r in ranks:
            if depth < len(r) and r[depth] not in seen:
                seen.add(r[depth])
                order.append(r[depth])
    return assemble(chunks, order, budget)


def window_attr(text: str, field: FieldSpec) -> str:
    chunks = exhaustive_chunks(text, CHUNK)
    return assemble(chunks, bm25_rank(chunks, attr_query(field)), ATTR_WINDOW)


# ---------------------------------------------------------------- model calls
def build_tasks(docs: list[Path], fields: list[FieldSpec]) -> list[dict[str, Any]]:
    tasks = []
    for path in docs:
        text = read_document(path)
        doc = path.name
        tasks.append({"strategy": "head", "doc": doc, "fields": [f.name for f in fields],
                      "prompt": render_prompt(truncate(text, WINDOW), fields, None)})
        tasks.append({"strategy": "window_1", "doc": doc, "fields": [f.name for f in fields],
                      "prompt": render_prompt(window_one(text, fields), fields, None)})
        tasks.append({"strategy": "window_small", "doc": doc, "fields": [f.name for f in fields],
                      "prompt": render_prompt(window_one(text, fields, SMALL_WINDOW), fields, None)})
        for f in fields:
            tasks.append({"strategy": "window_attr", "doc": doc, "fields": [f.name],
                          "prompt": render_prompt(window_attr(text, f), [f], None)})
        for chunk in exhaustive_chunks(text, EXHAUSTIVE_CHUNK):
            tasks.append({"strategy": "exhaustive", "doc": doc, "fields": [f.name for f in fields],
                          "chunk": chunk["index"], "prompt": render_prompt(chunk["text"], fields, None)})
    for task in tasks:
        task["sha"] = hashlib.sha256(task["prompt"].encode()).hexdigest()
    return tasks


def run(tasks: list[dict[str, Any]], workers: int) -> None:
    from quwarts.core.ledger import TokenLedger
    from quwarts.core.llm.openrouter import load_env_file, make_caller

    OUT.mkdir(parents=True, exist_ok=True)
    journal = OUT / "calls.jsonl"
    done = set()
    if journal.exists():
        done = {json.loads(line)["sha"] for line in journal.read_text().splitlines() if line.strip()}
    todo = [t for t in tasks if t["sha"] not in done]
    load_env_file(PROJECT / ".env")
    ledger = TokenLedger(theta=10**12)
    caller = make_caller(ledger, max_tokens=400)

    def one(task):
        text = caller.complete(task["prompt"], "long_doc_experiment", system=SYSTEM)
        tokens = ledger.records[-1].tokens
        row = {k: v for k, v in task.items() if k != "prompt"}
        row.update(response=text, tokens=tokens)
        with _lock, journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))


# ---------------------------------------------------------------- scoring
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}


def normalize_number(value: Any) -> float | None:
    """Commit-time unit standardization (compiler rule 9): currency marks and scale words."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = as_text(value).lower().replace(",", "")
    neg = text.strip().startswith("(") and text.strip().endswith(")")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    after = text[match.end():].strip()
    word = re.match(r"[a-z]+", after)
    if word and word.group(0) in _SCALE:
        number *= _SCALE[word.group(0)]
    return -abs(number) if neg else number


def cell(field: FieldSpec, pred: Any, gold: Any, tolerant: bool) -> float:
    numeric = field.value_type in ("int", "float")
    if numeric and not is_null(pred) and not is_null(gold):
        p, g = normalize_number(pred), normalize_number(gold)
        if p is not None and g is not None:
            if tolerant:
                return 1.0 if abs(p - g) <= 0.01 * max(abs(g), 1e-9) else 0.0
            return 1.0 if p == g else 0.0
    vt = "str" if field.value_type in ("int", "float") else field.value_type
    return value_score(pred, gold, vt)


def majority(values: list[Any]) -> Any:
    values = [v for v in values if not is_null(v)]
    if not values:
        return None
    counts = Counter(as_text(v).lower() for v in values)
    top = counts.most_common(1)[0][0]
    return next(v for v in values if as_text(v).lower() == top)


def outputs() -> tuple[dict, dict, dict]:
    """predictions[strategy][doc][field], tokens[strategy][doc], seen_text needs prompts (rebuilt)."""

    preds: dict[str, dict[str, dict[str, Any]]] = defaultdict(lambda: defaultdict(dict))
    tokens: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    chunks: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for line in (OUT / "calls.jsonl").read_text().splitlines():
        row = json.loads(line)
        tokens[row["strategy"]][row["doc"]] += row["tokens"]
        fields = parse_fields(row["response"])
        for name in row["fields"]:
            value = fields.get(name)
            if isinstance(value, list):
                value = " || ".join(map(str, value))
            if row["strategy"] == "exhaustive":
                chunks[row["doc"]][name].append(value)
            else:
                preds[row["strategy"]][row["doc"]][name] = value
    for doc, by_field in chunks.items():
        for name, values in by_field.items():
            preds["exhaustive"][doc][name] = majority(values)
    return preds, tokens


def stored_db(path: Path, docs: list[str], fields: list[FieldSpec]) -> dict[str, dict[str, Any]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    rows = {Path(r[0]).name: r for r in conn.execute(
        "SELECT doc_id, " + ", ".join(f'"{f.name}"' for f in fields) + " FROM finance")}
    return {d: ({f.name: rows[d][i + 1] for i, f in enumerate(fields)} if d in rows else {}) for d in docs}


def score(docs: list[Path], fields: list[FieldSpec]) -> dict[str, Any]:
    preds, tokens = outputs()
    names = [p.name for p in docs]
    preds["program"] = stored_db(RESULTS / "quwarts_finan_amortized_coverage_select" / "official.db", names, fields)
    preds["plumbing"] = stored_db(RESULTS / "quwarts_finan_plumbing" / "artifacts" / "databases" / "finan_plumbing.db",
                                  names, fields)
    # Gold is read only here, after every model output is stored.
    with open(PROJECT / "Query" / "Finan" / "Finan.csv") as handle:
        gold_rows = {f"{row['id']}.txt": {k.lower(): v for k, v in row.items()} for row in csv.DictReader(handle)}
    fields_by = {f.name: f for f in fields}
    report: dict[str, Any] = {"docs": names, "strategies": {}}
    for strategy in ["plumbing", "program", "window_small", "head", "window_1", "window_attr", "exhaustive"]:
        per_field: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for doc in names:
            gold = gold_rows.get(doc, {})
            for f in fields:
                g = gold.get(f.name.lower())
                p = preds[strategy].get(doc, {}).get(f.name)
                ref = preds["exhaustive"].get(doc, {}).get(f.name)
                per_field[f.name]["exact"].append(cell(f, p, g, False))
                per_field[f.name]["tol"].append(cell(f, p, g, True))
                if not is_null(g):
                    per_field[f.name]["exact_nonnull"].append(cell(f, p, g, False))
                    per_field[f.name]["tol_nonnull"].append(cell(f, p, g, True))
                per_field[f.name]["agree_exhaustive"].append(cell(f, p, ref, True))
        mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
        summary = {m: mean([x for f in per_field.values() for x in f[m]]) for m in
                   ["exact", "tol", "exact_nonnull", "tol_nonnull", "agree_exhaustive"]}
        spent = tokens.get(strategy, {})
        summary["tokens_per_doc"] = (sum(spent.values()) / len(names)) if spent else None
        summary["per_field_tol_nonnull"] = {k: mean(v["tol_nonnull"]) for k, v in per_field.items()}
        report["strategies"][strategy] = summary

    # Window recall: is the gold value's text inside what the model saw?
    recall: dict[str, list[float]] = defaultdict(list)
    for path in docs:
        text = read_document(path)
        gold = gold_rows.get(path.name, {})
        views = {"full": prepare_document(text), "head": prepare_document(truncate(text, WINDOW)),
                 "window_1": prepare_document(window_one(text, fields)),
                 "window_small": prepare_document(window_one(text, fields, SMALL_WINDOW))}
        for f in fields:
            g = gold.get(f.name.lower())
            if is_null(g) or f.value_type in ("int", "float") and normalize_number(g) is None:
                continue
            probe = g if f.value_type not in ("int", "float") else g.split(".0")[0]
            if find_span(probe, views["full"]) < 0:
                continue  # gold not written verbatim anywhere: recall undefined
            for name in ("head", "window_1", "window_small"):
                recall[name].append(1.0 if find_span(probe, views[name]) >= 0 else 0.0)
            recall["window_attr"].append(1.0 if find_span(probe, prepare_document(window_attr(text, f))) >= 0 else 0.0)
    report["window_recall_of_verbatim_gold"] = {k: (sum(v) / len(v), len(v)) for k, v in recall.items()}
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--plan", action="store_true", help="print task counts and token estimate only")
    args = parser.parse_args()
    spec = get_corpus("finan")
    fields = attributes(spec)
    docs = sample_docs(spec, args.docs)
    if args.plan or args.run:
        tasks = build_tasks(docs, fields)
        est = Counter()
        for t in tasks:
            est[t["strategy"]] += count_tokens(t["prompt"]) + 300
        print({k: (sum(1 for t in tasks if t["strategy"] == k), v) for k, v in est.items()}, "total", sum(est.values()))
        if args.run:
            run(tasks, args.workers)
    if args.score:
        report = score(docs, fields)
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str))
        for name, s in report["strategies"].items():
            fmt = lambda x: "  -  " if x is None else f"{x:.3f}"  # noqa: E731
            tok = "   -   " if s["tokens_per_doc"] is None else f"{s['tokens_per_doc']:>9,.0f}"
            print(f"{name:12} tokens/doc={tok} exact={fmt(s['exact'])} tol={fmt(s['tol'])} "
                  f"exact|gold={fmt(s['exact_nonnull'])} tol|gold={fmt(s['tol_nonnull'])} agree_exh={fmt(s['agree_exhaustive'])}")
        print("window recall (verbatim gold):", report["window_recall_of_verbatim_gold"])


if __name__ == "__main__":
    main()

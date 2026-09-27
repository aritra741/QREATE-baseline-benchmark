"""Go/no-go probe: list-then-count vs direct numeric read for count columns (AUDIT: grades with gold).

A column is a count column when its workload-generated meaning says it is a number of things (the
SQL aggregates it numerically and aliases name the unit). Arms, per document:
  direct   the system's current single-field read: the generated description, 10,108-token window
  list10   list the distinct counted items (template built only from the generated meaning),
           dedupe in code, count; same window
  list22   the same with a 22,000-token window (does the window limit recall?)
Gold is read only to grade. Pre-registered go condition, per column: the list arm's corpus mean is
within +-20% of the gold mean AND its share of documents within +-20% beats direct by >= 15 points.

    python -m quwarts.eval.router_count_probe --corpus legal --columns case_number legal_basis_num
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from quwarts.core.ledger import TokenLedger
from quwarts.core.router.comparator import as_number
from quwarts.core.router.context_probe import SYSTEM, V3, truncate
from quwarts.core.router.corpus_features import list_documents, read_document
from quwarts.core.router.probes import parse_fields
from quwarts.core.router.registry import PROJECT, RESULTS, get_corpus
from quwarts.core.retrieve_extract.tokens import count_tokens

SEED = 20260927
N_DOCS = 50
WINDOWS = {"direct": int(V3["window_tokens"]), "list10": int(V3["window_tokens"]), "list22": 22_000}
_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NONWORD = re.compile(r"[^a-z0-9]+")


def list_prompt(name: str, meaning: str, text: str) -> str:
    return (
        f"The column `{name}` is defined as: {meaning}\n"
        "This value is a count. Do not count. Instead, list every distinct item that this count counts, "
        "as it is named in the document. Give each distinct item once, by its full name.\n"
        'Return JSON only: {"items": ["...", "..."]}. If there are none, return {"items": []}.\n\n'
        f"Document:\n{text}"
    )


def direct_prompt(name: str, description: str, text: str) -> str:
    return (f"Extract this field from the document.\n- {name} (number): {description}\n"
            f'Return JSON only: {{"{name}": <number>}}.\n\nDocument:\n{text}')


def normalize_item(item: str) -> str:
    """Generic surface normalization for dedupe: drop bracketed citations, case, punctuation."""
    return _NONWORD.sub(" ", _BRACKETS.sub(" ", str(item).lower())).strip()


def parse_items(text: str) -> list[str] | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        items = json.loads(m.group(0)).get("items")
    except (json.JSONDecodeError, AttributeError):
        return None
    return [str(i) for i in items] if isinstance(items, list) else None


def summarize(pred: dict[str, float | None], gold: dict[str, float]) -> dict[str, Any]:
    docs = sorted(gold)
    p = {d: pred.get(d) for d in docs}
    ok = [d for d in docs if p[d] is not None]
    within = lambda d: p[d] is not None and abs(p[d] - gold[d]) <= 0.2 * max(gold[d], 1.0)
    gm = sum(gold.values()) / len(docs)
    pm = sum(p[d] for d in ok) / len(ok) if ok else None
    return {"n": len(docs), "parsed": len(ok), "exact": round(sum(p[d] == gold[d] for d in ok) / len(docs), 3),
            "within20_doc": round(sum(within(d) for d in docs) / len(docs), 3),
            "mae": round(sum(abs(p[d] - gold[d]) for d in ok) / len(ok), 2) if ok else None,
            "gold_mean": round(gm, 3), "pred_mean": round(pm, 3) if pm is not None else None,
            "mean_ratio": round(pm / gm, 3) if pm is not None and gm else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--columns", nargs="+", required=True)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--deadline", type=float, default=150.0)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)
    spec = get_corpus(args.corpus)
    table = spec.tables[0]
    descs = json.loads((RESULTS / "quwarts_router_v3" / spec.name / "shared_read_per_attribute"
                        / "descriptions_per_attribute.json").read_text())
    out = RESULTS / "quwarts_router_v3" / spec.name / "count_probe"
    out.mkdir(parents=True, exist_ok=True)
    cache_path = out / "calls.jsonl"
    cache = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            r = json.loads(line)
            cache[(r["arm"], r["column"], r["doc"])] = r
    paths = list_documents(spec.table(table.sql_name))
    sample = sorted(random.Random(SEED).sample(paths, N_DOCS), key=lambda p: p.name)
    (out / "sample.json").write_text(json.dumps([p.stem for p in sample]))

    if not args.report:
        from quwarts.core.llm.openrouter import load_env_file, make_caller
        load_env_file(PROJECT / ".env")
        ledger = TokenLedger(theta=10**12)
        callers = {"direct": make_caller(ledger, max_tokens=64), "list": make_caller(ledger, max_tokens=2000)}
        lock, t0 = threading.Lock(), time.time()
        tasks = []
        for col in args.columns:
            d = descs[f"{table.sql_name}.{col}"]
            for arm in WINDOWS:
                for path in sample:
                    if (arm, col, path.stem) not in cache:
                        tasks.append((arm, col, d, path))

        def run(task):
            arm, col, d, path = task
            if time.time() - t0 > args.deadline:
                return False
            text = truncate(read_document(path), WINDOWS[arm])
            if arm == "direct":
                prompt, caller = direct_prompt(col, d["description"], text), callers["direct"]
            else:
                prompt, caller = list_prompt(col, d["meaning"], text), callers["list"]
            response = caller.complete(prompt, "count_probe", system=SYSTEM, arm=arm, column=col, doc=path.stem)
            # Local tokenizer count: the shared ledger's last record is not thread-safe to read here.
            rec = {"arm": arm, "column": col, "doc": path.stem, "response": response,
                   "tokens": count_tokens(SYSTEM) + count_tokens(prompt) + count_tokens(response)}
            with lock, cache_path.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
            return True

        with ThreadPoolExecutor(args.workers) as pool:
            finished = sum(1 for done in pool.map(run, tasks) if done)
        print(json.dumps({"tasks": len(tasks), "finished": finished, "remaining": len(tasks) - finished,
                          "ledger_tokens": sum(r.tokens for r in ledger.records)}))
        return 0

    # Grading (gold) happens only here.
    from diagnostics.run_config_grid import load_ground_truth
    gold_rows = {str(r["id"]).strip(): r for r in load_ground_truth({"legal": "Legal"}.get(spec.name, spec.name))[table.sql_name]}
    report: dict[str, Any] = {"audit_only": True, "seed": SEED, "windows": WINDOWS, "columns": {}}
    for col in args.columns:
        gold = {d: as_number(gold_rows[d].get(col)) for d in (p.stem for p in sample)}
        gold = {d: v for d, v in gold.items() if v is not None}
        arms, tokens = {}, {}
        for arm in WINDOWS:
            pred: dict[str, float | None] = {}
            raw: dict[str, float | None] = {}
            tok = 0
            for doc in gold:
                rec = cache.get((arm, col, doc))
                if rec is None:
                    continue
                tok += int(rec["tokens"])
                if arm == "direct":
                    pred[doc] = as_number(parse_fields(rec["response"], [col]).get(col))
                else:
                    items = parse_items(rec["response"])
                    pred[doc] = None if items is None else float(len({normalize_item(i) for i in items if normalize_item(i)}))
                    raw[doc] = None if items is None else float(len(items))
            arms[arm] = summarize(pred, gold)
            if raw:
                arms[arm + "_no_dedupe"] = summarize(raw, gold)
            tokens[arm] = tok
        best = max(("list10", "list22"), key=lambda a: arms[a]["within20_doc"])
        go = (arms[best]["mean_ratio"] is not None and abs(arms[best]["mean_ratio"] - 1) <= 0.2
              and arms[best]["within20_doc"] - arms["direct"]["within20_doc"] >= 0.15)
        report["columns"][col] = {"arms": arms, "tokens": tokens, "best_list_arm": best, "go": go}
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

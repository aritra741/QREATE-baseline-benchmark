"""Count probe 2 (AUDIT: grades with gold): disambiguated, chunked, verified listing, and synthesized
regex extractors (EVAPORATE-style) for count columns.

Pre-registered, same documents and go rule as probe 1 (``router_count_probe``): per column, the arm's
corpus mean is within +-20% of the gold mean AND its share of documents within +-20% beats the direct
read by >= 15 points.

Stages (all gold-free except ``--report``):
  define  once per column: from the workload-generated meaning and corpus passages, the model states
          what one counted item is, how it is written (verbatim examples, checked in code), and what
          must not be counted (disambiguation before extraction, as in DFA / AGGBench).
  chunks  arm C: every document is split into 2,000-token chunks (whole document, no window cap);
          each chunk is asked for the counted items verbatim; code keeps items that occur in the
          chunk, unions across chunks, dedupes, counts. Run on the 50 evaluation documents and on 20
          disjoint selection documents.
  synth   arm E: the model writes K candidate regex sets from the definition and sample passages
          (patterns only, no code). The candidate whose per-document counts agree best with arm C on
          the 20 selection documents is applied to every evaluation document (no gold involved).

    python -m quwarts.eval.router_count_probe2 --corpus legal --columns case_number legal_basis_num --stage define
"""

from __future__ import annotations

import argparse
import json
import random
import re
import signal
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from quwarts.core.ledger import TokenLedger
from quwarts.core.retrieve_extract.tokens import count_tokens, encode_offsets
from quwarts.core.router.comparator import as_number
from quwarts.core.router.corpus_features import list_documents, read_document
from quwarts.core.router.registry import PROJECT, RESULTS, get_corpus
from quwarts.eval.router_count_probe import N_DOCS, SEED, normalize_item, parse_items, summarize

CHUNK = 2_000
OVERLAP = 100
N_SELECT = 20
K_CANDIDATES = 5
SYSTEM = "You read documents carefully and answer in JSON only."
_WS = re.compile(r"\s+")


def chunks(text: str) -> list[str]:
    if count_tokens(text) <= CHUNK:
        return [text]
    _ids, offsets = encode_offsets(text)
    out, start = [], 0
    while start < len(offsets):
        end = min(start + CHUNK, len(offsets))
        out.append(text[offsets[start][0]: offsets[end - 1][1]])
        if end == len(offsets):
            break
        start = end - OVERLAP
    return out


def squash(text: str) -> str:
    return _WS.sub(" ", text).strip().lower()


def parse_json(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        value = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def define_prompt(name: str, meaning: str, passages: list[str]) -> str:
    joined = "\n\n".join(f"Passage {i + 1}:\n{p}" for i, p in enumerate(passages))
    return (
        f"A database column `{name}` is defined as: {meaning}\n"
        "Its value is the number of distinct items of one kind that a document mentions. Using the passages "
        "below (from documents of this collection), state precisely what one counted item is, how such items "
        "are typically written in these documents, up to 5 short examples copied verbatim from the passages "
        "(only if they appear), and what must NOT be counted (things easily confused with an item, and "
        "repeated mentions of the same item).\n"
        'Return JSON only: {"item": "...", "written_as": "...", "examples": ["..."], "not_counted": ["..."]}\n\n'
        f"{joined}"
    )


def definition_text(d: dict[str, Any]) -> str:
    lines = [f"One counted item: {d.get('item', '')}", f"How items are written: {d.get('written_as', '')}"]
    if d.get("examples"):
        lines.append("Examples of items: " + "; ".join(d["examples"]))
    if d.get("not_counted"):
        lines.append("Do NOT count: " + "; ".join(map(str, d["not_counted"])))
    return "\n".join(lines)


def chunk_prompt(name: str, meaning: str, definition: str, passage: str) -> str:
    return (
        f"The column `{name}` is defined as: {meaning}\n{definition}\n\n"
        "List every counted item that appears in the passage below. Copy each item exactly as it is written "
        "in the passage. List each distinct item once. If none appears, return an empty list.\n"
        'Return JSON only: {"items": ["..."]}\n\n'
        f"Passage:\n{passage}"
    )


def synth_prompt(name: str, meaning: str, definition: str, passages: list[str]) -> str:
    joined = "\n\n".join(f"Passage {i + 1}:\n{p}" for i, p in enumerate(passages))
    return (
        f"The column `{name}` is defined as: {meaning}\n{definition}\n\n"
        "Write Python regular expressions (Python `re` syntax, applied with re.finditer to the whole document) "
        "that find every counted item in documents like the passages below. Each match must be one mention of "
        "one item. If a pattern has a capturing group, group 1 must be the part that identifies the item, so "
        "that repeated mentions of the same item give the same text.\n"
        'Return JSON only: {"patterns": ["...", "..."]}\n\n'
        f"{joined}"
    )


class _Timeout(Exception):
    pass


def _alarm(_sig, _frame):
    raise _Timeout


def regex_count(patterns: list[str], text: str, seconds: int = 2) -> int | None:
    """Distinct items matched by the patterns (union, normalized). None if every pattern is unusable."""
    found: set[str] = set()
    usable = 0
    signal.signal(signal.SIGALRM, _alarm)
    for pat in patterns:
        try:
            rx = re.compile(pat)
        except (re.error, TypeError, RecursionError):
            continue
        signal.alarm(seconds)
        try:
            for m in rx.finditer(text):
                value = m.group(1) if rx.groups and m.group(1) else m.group(0)
                key = normalize_item(value)
                if key:
                    found.add(key)
            usable += 1
        except _Timeout:
            pass
        finally:
            signal.alarm(0)
    return len(found) if usable else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--columns", nargs="+", required=True)
    parser.add_argument("--stage", choices=["define", "chunks", "synth", "report"], required=True)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--deadline", type=float, default=140.0)
    args = parser.parse_args(argv)
    spec = get_corpus(args.corpus)
    table = spec.tables[0]
    descs = json.loads((RESULTS / "quwarts_router_v3" / spec.name / "shared_read_per_attribute"
                        / "descriptions_per_attribute.json").read_text())
    out = RESULTS / "quwarts_router_v3" / spec.name / "count_probe2"
    out.mkdir(parents=True, exist_ok=True)
    cache_path = out / "calls.jsonl"
    cache: dict[tuple, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text().splitlines():
            r = json.loads(line)
            cache[tuple(r["key"])] = r
    paths = list_documents(spec.table(table.sql_name))
    evaluation = sorted(random.Random(SEED).sample(paths, N_DOCS), key=lambda p: p.name)  # probe 1's sample
    in_eval = set(evaluation)
    rest = [p for p in paths if p not in in_eval]
    selection = sorted(random.Random(SEED + 1).sample(rest, N_SELECT), key=lambda p: p.name)
    (out / "documents.json").write_text(json.dumps({"evaluation": [p.stem for p in evaluation],
                                                    "selection": [p.stem for p in selection]}))
    doc_chunks = {p.stem: chunks(read_document(p)) for p in evaluation + selection}

    lock, t0 = threading.Lock(), time.time()
    callers: dict[str, Any] = {}

    def caller(kind: str):
        if not callers:
            from quwarts.core.llm.openrouter import load_env_file, make_caller
            load_env_file(PROJECT / ".env")
            ledger = TokenLedger(theta=10**12)
            callers["define"] = make_caller(ledger, max_tokens=700)
            callers["chunk"] = make_caller(ledger, max_tokens=1200)
            callers["synth"] = make_caller(ledger, temperature=0.8, max_tokens=700)
        return callers[kind]

    def call(key: tuple, kind: str, prompt: str) -> bool:
        if key in cache:
            return True
        if time.time() - t0 > args.deadline:
            return False
        response = caller(kind).complete(prompt, "count_probe2", system=SYSTEM, key="/".join(map(str, key)))
        rec = {"key": list(key), "response": response,
               "tokens": count_tokens(SYSTEM) + count_tokens(prompt) + count_tokens(response)}
        with lock:
            cache[key] = rec
            with cache_path.open("a") as fh:
                fh.write(json.dumps(rec) + "\n")
        return True

    def passages_for(col: str, salt: int) -> list[str]:
        rng = random.Random(f"{SEED}:{col}:{salt}")
        docs = rng.sample(selection, 3)
        return [rng.choice(doc_chunks[p.stem]) for p in docs]

    def definition(col: str) -> str:
        rec = cache[("define", col)]
        d = parse_json(rec["response"]) or {}
        passages = squash(" ".join(passages_for(col, 0)))
        d["examples"] = [e for e in d.get("examples") or [] if isinstance(e, str) and squash(e) in passages]
        return definition_text(d)

    if args.stage == "define":
        for col in args.columns:
            call(("define", col), "define", define_prompt(col, descs[f"{table.sql_name}.{col}"]["meaning"], passages_for(col, 0)))
            print(col, "\n", definition(col), "\n")
        return 0

    if args.stage == "chunks":
        tasks = []
        for col in args.columns:
            meaning, dtext = descs[f"{table.sql_name}.{col}"]["meaning"], definition(col)
            for p in evaluation + selection:
                for i, ch in enumerate(doc_chunks[p.stem]):
                    tasks.append((("chunk", col, p.stem, i), chunk_prompt(col, meaning, dtext, ch)))
        with ThreadPoolExecutor(args.workers) as pool:
            done = sum(pool.map(lambda t: call(t[0], "chunk", t[1]), tasks))
        print(json.dumps({"tasks": len(tasks), "done": done, "remaining": len(tasks) - done}))
        return 0

    if args.stage == "synth":
        tasks = []
        for col in args.columns:
            meaning, dtext = descs[f"{table.sql_name}.{col}"]["meaning"], definition(col)
            for k in range(K_CANDIDATES):
                tasks.append((("synth", col, k), synth_prompt(col, meaning, dtext, passages_for(col, k + 1))))
        with ThreadPoolExecutor(args.workers) as pool:
            done = sum(pool.map(lambda t: call(t[0], "synth", t[1]), tasks))
        print(json.dumps({"tasks": len(tasks), "done": done}))
        return 0

    # --- report: gold is read only here ---------------------------------------------------------
    from diagnostics.run_config_grid import load_ground_truth
    gold_rows = {str(r["id"]).strip(): r for r in load_ground_truth({"legal": "Legal"}.get(spec.name, spec.name))[table.sql_name]}
    probe1 = {}
    p1 = RESULTS / "quwarts_router_v3" / spec.name / "count_probe" / "report.json"
    if p1.exists():
        probe1 = json.loads(p1.read_text())["columns"]
    report: dict[str, Any] = {"audit_only": True, "chunk_tokens": CHUNK, "k_candidates": K_CANDIDATES, "columns": {}}
    for col in args.columns:
        def chunk_count(stem: str) -> float | None:
            items: set[str] = set()
            for i, ch in enumerate(doc_chunks[stem]):
                rec = cache.get(("chunk", col, stem, i))
                if rec is None:
                    return None
                listed = parse_items(rec["response"]) or []
                hay = squash(ch)
                items |= {normalize_item(x) for x in listed if squash(x) and squash(x) in hay and normalize_item(x)}
            return float(len(items))

        def chunk_count_unverified(stem: str) -> float | None:
            items: set[str] = set()
            for i in range(len(doc_chunks[stem])):
                rec = cache.get(("chunk", col, stem, i))
                if rec is None:
                    return None
                items |= {normalize_item(x) for x in parse_items(rec["response"]) or [] if normalize_item(x)}
            return float(len(items))

        candidates = []
        for k in range(K_CANDIDATES):
            rec = cache.get(("synth", col, k))
            pats = (parse_json(rec["response"]) or {}).get("patterns") if rec else None
            candidates.append([p for p in pats if isinstance(p, str)] if isinstance(pats, list) else [])
        texts = {p.stem: read_document(p) for p in evaluation + selection}
        counts = {k: {s: regex_count(c, texts[s]) for s in texts} if c else {} for k, c in enumerate(candidates)}
        arm_c_sel = {p.stem: chunk_count(p.stem) for p in selection}

        def disagreement(k: int) -> float:
            pairs = [(counts[k].get(s), arm_c_sel[s]) for s in arm_c_sel]
            pairs = [(a, b) for a, b in pairs if a is not None and b is not None]
            return statistics.mean(abs(a - b) for a, b in pairs) if len(pairs) >= N_SELECT // 2 else float("inf")

        ranked = sorted(range(K_CANDIDATES), key=disagreement)
        chosen = ranked[0]
        gold = {p.stem: as_number(gold_rows[p.stem].get(col)) for p in evaluation}
        gold = {d: v for d, v in gold.items() if v is not None}
        arms = {
            "chunk_verified": summarize({d: chunk_count(d) for d in gold}, gold),
            "chunk_unverified": summarize({d: chunk_count_unverified(d) for d in gold}, gold),
            "regex_selected": summarize({d: (None if counts[chosen].get(d) is None else float(counts[chosen][d])) for d in gold}, gold),
            "regex_median_of_k": summarize({d: (statistics.median(v) if (v := [counts[k][d] for k in counts if counts[k].get(d) is not None]) else None) for d in gold}, gold),
        }
        for name in ("direct", "list10", "list22"):
            if name in probe1.get(col, {}).get("arms", {}):
                arms[name + "_probe1"] = probe1[col]["arms"][name]
        direct = arms.get("direct_probe1", {}).get("within20_doc", 0.0)
        go = {a: bool(s["mean_ratio"] is not None and abs(s["mean_ratio"] - 1) <= 0.2 and s["within20_doc"] - direct >= 0.15)
              for a, s in arms.items() if not a.endswith("_probe1")}
        tok = lambda pred: sum(r["tokens"] for key, r in cache.items() if pred(key))
        eval_stems = {p.stem for p in evaluation}
        report["columns"][col] = {
            "definition": definition(col),
            "candidates": candidates,
            "candidate_disagreement_on_selection": {k: disagreement(k) for k in range(K_CANDIDATES)},
            "chosen_candidate": chosen,
            "arms": arms,
            "go": go,
            "tokens": {"define": tok(lambda k: k[0] == "define" and k[1] == col),
                       "chunk_eval_docs": tok(lambda k: k[0] == "chunk" and k[1] == col and k[2] in eval_stems),
                       "chunk_selection_docs": tok(lambda k: k[0] == "chunk" and k[1] == col and k[2] not in eval_stems),
                       "synth": tok(lambda k: k[0] == "synth" and k[1] == col),
                       "regex_per_document": 0},
        }
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

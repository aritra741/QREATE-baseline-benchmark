"""Second looks by a stronger reader, routed by a per-column repair rate (SYSTEM_PLAN.md, component 4).

The label-free verifier finds wrong cells but not repairable ones (I2b); the repair rate of a column, estimated from
ten labelled cells, routes a budget of second looks three times better than random (the column-rate result). So:
for each column just read, if a labelled sample is available (``QUWARTS_REPAIR_LABELS``: {"table.column": {doc:
gold}}), the stronger reader re-reads the labelled documents alone; the net rate (fixes minus breaks, per look) is
the column's repair rate; columns with a positive rate get second looks on their other documents, cheapest first,
until the budget (a share of the extraction's tokens, at the stronger reader's price) is spent. Every call is
journaled with its tokens, and the stream charges them separately.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from quwarts.core.router.comparator import is_null
from quwarts.core.router.context_probe import FieldSpec, render_prompt, truncate
from quwarts.core.router.corpus_features import read_document
from quwarts.core.router.probes import parse_fields
from quwarts.core.retrieve_extract.tokens import count_tokens

SYSTEM = "Extract only facts stated in the document. Return JSON."
MODEL = os.environ.get("QUWARTS_REPAIR_MODEL", "qwen2.5:32b-instruct")
SHARE = float(os.environ.get("QUWARTS_REPAIR_SHARE", 0.25))  # of the extraction's tokens, as the second reader's budget
MIN_LABELLED = 8
_lock = threading.Lock()


def server() -> dict | None:
    """The stronger reader's server (results/experiments/servers/qwen32b.json), None when it is not up."""
    from quwarts.eval.drift_run import RESULTS

    p = RESULTS.parent / "results" / "experiments" / "servers" / "qwen32b.json"
    return json.loads(p.read_text()) if p.exists() else None


def chat(host: str, prompt: str, num_ctx: int, max_tokens: int = 700) -> dict:
    import httpx

    body = {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "stream": False, "options": {"temperature": 0.1, "num_predict": max_tokens, "num_ctx": num_ctx},
            "keep_alive": "60m"}
    r = httpx.post(f"http://{host}/api/chat", json=body, timeout=600.0)
    r.raise_for_status()
    j = r.json()
    return {"response": j["message"]["content"], "prompt_tokens": int(j.get("prompt_eval_count") or 0),
            "output_tokens": int(j.get("eval_count") or 0)}


class Repairer:
    """One per stream: labelled samples, estimated rates, a journal of the stronger reader's calls."""

    def __init__(self, journal: Path, labels_path: str | None, correct):
        self.journal = journal
        self.labels = json.loads(Path(labels_path).read_text()) if labels_path else {}
        self.correct = correct  # (served, gold) -> bool, the benchmark's cell comparison
        self.rates: dict[str, float] = {}
        self.done: dict[str, dict] = {}
        if journal.exists():
            for line in journal.read_text().splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.done[r["prompt_sha"]] = r
        self.srv = server()

    def available(self) -> bool:
        return bool(self.labels) and self.srv is not None

    def _ask(self, text: str, f: FieldSpec, meta: dict) -> dict:
        prompt = render_prompt(truncate(text, int(self.srv["context"]) - 1500), [f], None)
        sha = hashlib.sha256(prompt.encode()).hexdigest()
        if sha in self.done:
            return {**self.done[sha], "cached": True}
        res = chat(self.srv["host"], prompt, int(self.srv["context"]))
        row = {"prompt_sha": sha, "model": MODEL, **meta, **res, "prompt_tokens_est": count_tokens(prompt)}
        with _lock:
            with self.journal.open("a") as h:
                h.write(json.dumps(row, default=str) + "\n")
            self.done[sha] = row
        return {**row, "cached": False}

    def value(self, res: dict, a: str):
        return parse_fields(res["response"], [a]).get(a)

    def estimate(self, table: str, a: str, f: FieldSpec, docs: dict[str, Path], served: dict[str, Any], workers: int) -> dict:
        """The column's net repair rate from its labelled sample (fixes minus breaks per look)."""
        col = f"{table}.{a}"
        if col in self.rates:
            return {"rate": self.rates[col], "cached": True}
        labelled = {d: g for d, g in self.labels.get(col, {}).items() if d in docs}
        if len(labelled) < MIN_LABELLED:
            self.rates[col] = float("nan")
            return {"rate": None, "reason": f"{len(labelled)} labelled documents"}
        texts = {d: read_document(docs[d]) for d in labelled}
        fixes = breaks = 0
        calls = []

        def one(d):
            return d, self._ask(texts[d], f, {"table": table, "doc": d, "attribute": a, "purpose": "estimate"})

        with ThreadPoolExecutor(max_workers=workers) as ex:
            for d, res in ex.map(one, list(labelled)):
                calls.append(res)
                before, after = self.correct(served.get(d), labelled[d]), self.correct(self.value(res, a), labelled[d])
                fixes += (not before) and after
                breaks += before and not after
        rate = (fixes - breaks) / len(labelled)
        self.rates[col] = rate
        return {"rate": round(rate, 3), "fixes": fixes, "breaks": breaks, "labelled": len(labelled),
                "calls": sum(not r.get("cached") for r in calls),
                "tokens": sum(r["prompt_tokens"] + r["output_tokens"] for r in calls if not r.get("cached"))}

    def route(self, table: str, attrs: list[str], fields: dict[str, FieldSpec], docs: dict[str, Path], served: dict,
              budget_tokens: int, workers: int) -> dict:
        """Second looks for the columns with a positive rate, cheapest documents first, within the budget.
        Returns the replacements {(doc, attr): value} and the accounting."""
        cells = []
        for a in attrs:
            col = f"{table}.{a}"
            rate = self.rates.get(col)
            if rate is None or rate != rate or rate <= 0:
                continue
            for d, p in docs.items():
                if d in self.labels.get(col, {}):
                    continue  # the labelled sample has been read already
                cells.append((rate, d, a))
        if not cells or budget_tokens <= 0:
            return {"updates": {}, "calls": 0, "tokens": 0, "cells_considered": len(cells)}
        sizes = {d: count_tokens(read_document(docs[d])) for d in {d for _, d, _ in cells}}
        cells.sort(key=lambda x: (-(x[0] / max(1, sizes[x[1]])), x[1], x[2]))  # rate per token, then name
        chosen, spent = [], 0
        for rate, d, a in cells:
            est = min(sizes[d], int(self.srv["context"]) - 1500) + 300
            if spent + est > budget_tokens:
                continue
            spent += est
            chosen.append((d, a))
        updates, calls, tokens = {}, 0, 0
        texts = {d: read_document(docs[d]) for d in {d for d, _ in chosen}}

        def one(x):
            d, a = x
            return d, a, self._ask(texts[d], fields[f"{table}.{a}"], {"table": table, "doc": d, "attribute": a, "purpose": "second_look"})

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for d, a, res in ex.map(one, chosen):
                updates[(d, a)] = self.value(res, a)
                if not res.get("cached"):
                    calls += 1
                    tokens += res["prompt_tokens"] + res["output_tokens"]
        return {"updates": updates, "calls": calls, "tokens": tokens, "cells_considered": len(cells),
                "cells_asked": len(chosen), "budget_tokens": budget_tokens, "seconds": round(time.time() - t0, 1)}

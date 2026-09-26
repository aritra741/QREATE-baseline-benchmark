"""Budgeted, gold-free corpus probes.

For each probed attribute the probe estimates:

* ``kappa``  self-consistency: agreement of two identical canonical requests
* ``g``      extractiveness: share of non-null answers that are spans of the source
* ``delta``  query sensitivity: conflict rate between canonical and query-conditioned
             answers when both are non-null, minus the conflict rate of two identical requests
* ``recall_gap`` net share of informative pairs where query context finds a value the
             canonical request missed, minus presence noise between identical requests
* ``delta_cross`` conflict rate between two query-conditioned requests

A metric backed by fewer than ``probe_min_pairs`` pairs (or ``probe_min_values``
values) is reported as None, and the policy falls back to its prior.
* ``r``      anchor regularity: share of grounded values that share one textual cue

Every prompt and raw response is journaled. No gold and no baseline outputs
are read.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from quwarts.core.corpus_probe.context import exhaustive_chunks
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.core.router.constants import FROZEN
from quwarts.core.router.corpus_features import length_stratified_sample, list_documents, read_document
from quwarts.core.router.registry import CorpusSpec
from quwarts.core.router.text import anchor, find_span, is_null, normalize, prepare_document
from quwarts.core.router.workload_features import AttributeUse

SYSTEM = "Extract only facts stated in the document. Return JSON."
COMPLETION_TOKENS = 280
_STOP = {"the", "and", "for", "with", "from", "that", "this", "use", "format", "e.g", "name", "number", "extract", "only", "first", "leave", "empty", "applicable", "multiple", "mentioned"}


def _field_lines(uses: list[AttributeUse]) -> str:
    lines = []
    for use in uses:
        kind = "number" if use.numeric else "text"
        line = f"- {use.name} ({kind}): {use.description or use.name.replace('_', ' ')}"
        if use.literals:
            line += f"\n  workload labels: {', '.join(use.literals[:12])}"
        lines.append(line)
    return "\n".join(lines)


def canonical_prompt(document: str, uses: list[AttributeUse]) -> str:
    return (
        "Extract the following fields about the single entity described in the document.\n"
        "Use null when a field is not stated. Copy values as written when possible.\n\n"
        f"DOCUMENT:\n{document}\n\nFIELDS:\n{_field_lines(uses)}\n\n"
        'Return JSON with this shape and no other keys: {"fields": {"<field>": <value or null>}}'
    )


def query_prompt(document: str, sql: str, uses: list[AttributeUse]) -> str:
    return (
        "The fields below are inputs to the SQL query shown. Extract each field's value for the\n"
        "single entity described in the document, as the query intends it. Do not answer the query.\n"
        "Use null when a field is not stated. Do not copy SQL constants unless the document supports them.\n\n"
        f"DOCUMENT:\n{document}\n\nSQL context:\n{sql}\n\nFIELDS:\n{_field_lines(uses)}\n\n"
        'Return JSON with this shape and no other keys: {"fields": {"<field>": <value or null>}}'
    )


def _keywords(uses: list[AttributeUse]) -> set[str]:
    words: set[str] = set()
    for use in uses:
        words.update(part for part in use.name.lower().split("_") if len(part) > 2)
        words.update(
            word for word in re.findall(r"[a-z]{4,}", (use.description or "").lower()) if word not in _STOP
        )
        words.update(label.lower() for label in use.literals if len(label) > 2)
    return words


def probe_window(text: str, uses: list[AttributeUse], budget: int | None = None) -> str:
    """Whole document if it fits the probe window; else the most field-relevant chunks in order."""

    budget = budget or int(FROZEN["window_tokens"])
    if count_tokens(text) <= budget:
        return text
    words = _keywords(uses)
    chunks = exhaustive_chunks(text, max_tokens=600)
    scored = []
    for chunk in chunks:
        lowered = chunk["text"].lower()
        scored.append((sum(lowered.count(word) for word in words), -chunk["index"], chunk))
    chosen, used = [], 0
    for _score, _neg, chunk in sorted(scored, key=lambda row: (row[0], row[1]), reverse=True):
        if used + chunk["tokens"] > budget:
            continue
        chosen.append(chunk)
        used += chunk["tokens"]
    chosen.sort(key=lambda chunk: chunk["index"])
    return "\n...\n".join(chunk["text"] for chunk in chosen)


def parse_fields(text: str) -> dict[str, Any]:
    body = (text or "").strip()
    body = re.sub(r"^```(?:json)?|```$", "", body, flags=re.M).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        payload = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("fields"), dict):
        return payload["fields"]
    return payload if isinstance(payload, dict) else {}


def _as_number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def same_value(left: Any, right: Any) -> bool:
    if is_null(left) and is_null(right):
        return True
    if is_null(left) or is_null(right):
        return False
    a, b = _as_number(left), _as_number(right)
    if a is not None and b is not None:
        return abs(a - b) <= 1e-6 * max(1.0, abs(a), abs(b))
    return normalize(left) == normalize(right)


def _scalar(value: Any) -> Any:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value) if value else None
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value


@dataclass
class AttributeProbe:
    qualified: str
    canonical: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # doc -> (rep1, rep2)
    conditioned: list[tuple[str, str, Any]] = field(default_factory=list)  # (doc, query_id, value)

    def metrics(self, documents_lower: dict[str, str]) -> dict[str, Any]:
        min_pairs = int(FROZEN["probe_min_pairs"])
        min_values = int(FROZEN["probe_min_values"])

        # Noise floor from two identical canonical requests, split into
        # value noise (both answer, differently) and presence noise (one is null).
        canon_pairs = list(self.canonical.values())
        c_both, c_one = _split(canon_pairs)
        c_informative = len(c_both) + len(c_one)
        kappa = (sum(same_value(a, b) for a, b in c_both) + 0) / c_informative if c_informative else None
        value_noise = (sum(not same_value(a, b) for a, b in c_both) / len(c_both)) if c_both else 0.0
        presence_noise = (len(c_one) / c_informative) if c_informative else 0.0

        values = [(doc, v) for doc, (a, b) in self.canonical.items() for v in (a, b)]
        values += [(doc, v) for doc, _q, v in self.conditioned]
        non_null = [(doc, v) for doc, v in values if not is_null(v)]
        spans = [(doc, find_span(v, documents_lower[doc])) for doc, v in non_null]
        g = (sum(1 for _doc, offset in spans if offset >= 0) / len(spans)) if len(spans) >= min_values else None

        # Canonical versus query-conditioned, per document.
        pairs: list[tuple[Any, Any]] = []
        cross_pairs: list[tuple[Any, Any]] = []
        by_doc: dict[str, list[Any]] = {}
        for doc, _query, value in self.conditioned:
            by_doc.setdefault(doc, []).append(value)
        for doc, conditioned in by_doc.items():
            reference = self.canonical.get(doc, (None, None))[0]
            pairs.extend((reference, value) for value in conditioned)
            for i in range(len(conditioned)):
                for j in range(i + 1, len(conditioned)):
                    cross_pairs.append((conditioned[i], conditioned[j]))
        both, one = _split(pairs)
        # Conflict: both answer and the answers differ. This is what makes one shared value wrong.
        conflict_raw = (sum(not same_value(a, b) for a, b in both) / len(both)) if len(both) >= min_pairs else None
        delta = None if conflict_raw is None else max(0.0, conflict_raw - value_noise)
        # Recall gap: query context finds a value the canonical request missed (net of the reverse).
        informative = len(both) + len(one)
        found = sum(1 for a, b in one if is_null(a) and not is_null(b))
        lost = sum(1 for a, b in one if not is_null(a) and is_null(b))
        recall_raw = ((found - lost) / informative) if informative >= min_pairs else None
        recall_gap = None if recall_raw is None else max(0.0, recall_raw - presence_noise)
        x_both, _x_one = _split(cross_pairs)
        cross_raw = (sum(not same_value(a, b) for a, b in x_both) / len(x_both)) if len(x_both) >= min_pairs else None
        delta_cross = None if cross_raw is None else max(0.0, cross_raw - value_noise)

        anchors = []
        for doc, (first, _second) in self.canonical.items():
            if is_null(first):
                continue
            offset = find_span(first, documents_lower[doc])
            if offset >= 0:
                anchors.append(anchor(documents_lower[doc], offset))
        anchors = [cue for cue in anchors if cue]
        r = (Counter(anchors).most_common(1)[0][1] / len(anchors)) if len(anchors) >= min_values else None

        canonical_answers = [v for a, b in self.canonical.values() for v in (a, b)]
        null_rate = (sum(is_null(v) for v in canonical_answers) / len(canonical_answers)) if canonical_answers else None
        return {
            "n_docs": len(self.canonical),
            "n_conditioned": len(self.conditioned),
            "n_values": len(spans),
            "kappa": kappa,
            "value_noise": value_noise,
            "presence_noise": presence_noise,
            "g": g,
            "conflict_raw": conflict_raw,
            "delta": delta,
            "n_conflict_pairs": len(both),
            "recall_raw": recall_raw,
            "recall_gap": recall_gap,
            "n_recall_pairs": informative,
            "delta_cross_raw": cross_raw,
            "delta_cross": delta_cross,
            "n_cross_pairs": len(x_both),
            "r": r,
            "n_anchors": len(anchors),
            "null_rate": null_rate,
        }


def _split(pairs: list[tuple[Any, Any]]) -> tuple[list[tuple[Any, Any]], list[tuple[Any, Any]]]:
    """(both non-null, exactly one non-null). Pairs where both are null carry no evidence."""

    both = [(a, b) for a, b in pairs if not is_null(a) and not is_null(b)]
    one = [(a, b) for a, b in pairs if is_null(a) != is_null(b)]
    return both, one


def choose_contexts(contexts: list[str], uses: list[AttributeUse], seen: Counter, n: int) -> list[str]:
    """Pick query contexts for one document so every probed attribute is seen evenly.

    Each candidate scores sum(1 / (1 + times the attribute was already seen)).
    """

    chosen: list[str] = []
    for _ in range(min(n, len(contexts))):
        best, best_score = None, 0.0
        for query_id in contexts:
            if query_id in chosen:
                continue
            score = sum(1.0 / (1 + seen[use.qualified]) for use in uses if query_id in use.query_ids)
            if score > best_score:
                best, best_score = query_id, score
        if best is None:
            break
        chosen.append(best)
        for use in uses:
            if best in use.query_ids:
                seen[use.qualified] += 1
    return chosen


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _call_cost_estimate(doc_tokens: int) -> int:
    return min(doc_tokens, int(FROZEN["window_tokens"])) + int(FROZEN["call_overhead_tokens"]) + COMPLETION_TOKENS


def plan_probe(
    spec: CorpusSpec,
    uses: list[AttributeUse],
    queries: dict[str, str],
    doc_tokens: dict[str, dict[str, int]],
    budget: int,
) -> dict[str, Any]:
    """Allocate the probe budget over tables in proportion to probed attributes."""

    by_table: dict[str, list[AttributeUse]] = {}
    for use in uses:
        by_table.setdefault(use.table, []).append(use)
    total_attrs = sum(len(items) for items in by_table.values()) or 1
    plan: dict[str, Any] = {}
    for table, items in sorted(by_table.items()):
        share = budget * len(items) / total_attrs
        tokens = doc_tokens[table]
        mean_call = sum(_call_cost_estimate(value) for value in tokens.values()) / max(1, len(tokens))
        contexts = [qid for qid in sorted(queries) if any(qid in use.query_ids for use in items)]
        calls_per_doc = 2 + min(int(FROZEN["probe_query_contexts_per_doc"]), len(contexts))
        k = int(share // (calls_per_doc * mean_call)) if mean_call else 0
        k = min(int(FROZEN["probe_docs_max"]), k, len(tokens))
        plan[table] = {
            "attributes": [use.qualified for use in items],
            "docs": k,
            "affordable": k >= int(FROZEN["probe_docs_min"]),
            "calls_per_doc": calls_per_doc,
            "mean_call_tokens": mean_call,
            "share_tokens": share,
            "contexts": contexts,
        }
    return plan


def run_probe(
    spec: CorpusSpec,
    uses: list[AttributeUse],
    queries: dict[str, str],
    doc_tokens: dict[str, dict[str, int]],
    caller: BudgetedCaller,
    journal: Path | None = None,
    budget: int | None = None,
) -> dict[str, Any]:
    budget = budget if budget is not None else caller.ledger.remaining()
    plan = plan_probe(spec, uses, queries, doc_tokens, budget)
    by_name = {use.qualified: use for use in uses}
    results: dict[str, Any] = {}
    exhausted = False

    def log(row: dict[str, Any]) -> None:
        if journal is None:
            return
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")

    def call(prompt: str, meta: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal exhausted
        if exhausted:
            return None
        try:
            text = caller.complete(prompt, "router_probe", system=SYSTEM, **meta)
        except BudgetExhausted:
            exhausted = True
            return None
        spent = caller.ledger.records[-1].tokens if caller.ledger.records else None
        log({**meta, "prompt_sha": _sha(prompt), "prompt": prompt, "response": text, "tokens": spent})
        return parse_fields(text)

    for table, entry in plan.items():
        table_uses = [by_name[name] for name in entry["attributes"]]
        probes = {use.qualified: AttributeProbe(use.qualified) for use in table_uses}
        if not entry["affordable"]:
            results[table] = {"plan": entry, "metrics": {}}
            continue
        table_spec = spec.table(table)
        paths = list_documents(table_spec)
        sample = length_stratified_sample(paths, doc_tokens[table], entry["docs"], f"probe:{table}")
        lowered: dict[str, str] = {}
        contexts = entry["contexts"]
        seen: Counter = Counter()
        for index, path in enumerate(sample):
            raw = read_document(path)
            lowered[path.name] = prepare_document(raw)
            window = probe_window(raw, table_uses)
            prompt = canonical_prompt(window, table_uses)
            reps = []
            for rep in (1, 2):
                meta = {"table": table, "doc": path.name, "kind": "canonical", "rep": rep}
                reps.append(call(prompt, meta) or {})
            for use in table_uses:
                probes[use.qualified].canonical[path.name] = (
                    _scalar(reps[0].get(use.name)),
                    _scalar(reps[1].get(use.name)),
                )
            chosen = choose_contexts(contexts, table_uses, seen, int(FROZEN["probe_query_contexts_per_doc"]))
            for query_id in dict.fromkeys(chosen):
                q_uses = [use for use in table_uses if query_id in use.query_ids]
                if not q_uses:
                    continue
                q_window = probe_window(raw, q_uses)
                fields = call(
                    query_prompt(q_window, queries[query_id], q_uses),
                    {"table": table, "doc": path.name, "kind": "conditioned", "query_id": query_id},
                ) or {}
                for use in q_uses:
                    probes[use.qualified].conditioned.append((path.name, query_id, _scalar(fields.get(use.name))))
        results[table] = {
            "plan": entry,
            "sample": [path.name for path in sample],
            "metrics": {name: probe.metrics(lowered) for name, probe in probes.items()},
        }
    return {"budget": budget, "exhausted": exhausted, "tables": results}


def fake_caller_factory(responder: Callable[[str, dict[str, Any]], str]):
    """Test helper: a BudgetedCaller over a deterministic responder."""

    from quwarts.core.ledger import TokenLedger

    def build(theta: int) -> BudgetedCaller:
        ledger = TokenLedger(theta=theta)

        def client(prompt: str, metadata: dict[str, Any]) -> tuple[str, int]:
            text = responder(prompt, metadata)
            return text, max(1, (len(prompt) + len(text)) // 4)

        return BudgetedCaller(ledger, client)

    return build

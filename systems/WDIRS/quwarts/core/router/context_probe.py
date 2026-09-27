"""Paired context sampling for router-v3.

A *context* is how a column is read: ``CANONICAL`` (no query, all of a table's
needed attributes in one bundle) or one reference-workload query (its SQL shown,
only its attributes). A read is one whole-document call, truncated to the same
window the operators use, so the probe measures the operator that would run.

Distances between needs need *paired* observations: the same document read under
both contexts. Reads are chosen greedily by value of information per token:
each candidate (document, context) earns sum(w / (1 + n)) over the need pairs it
would add, where n is how many observations that pair already has. This spreads
reads so every pair the plan depends on is measured, instead of spending the
budget on a few contexts. A fixed number of repeated reads per context supplies
the noise floor. Every prompt and raw response is journaled.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.retrieve_extract.tokens import count_tokens, encode_offsets
from quwarts.core.router.corpus_features import length_stratified_sample, list_documents, read_document
from quwarts.core.router.needs import CANONICAL, Need
from quwarts.core.router.probes import parse_fields
from quwarts.core.router.registry import CorpusSpec

SYSTEM = "Extract only facts stated in the document. Return JSON."

V3: dict[str, Any] = {
    "window_tokens": 10_108,  # corpus_probe.context whole-document budget
    "call_overhead_tokens": 600,
    "pool_docs_per_table": 40,
    "noise_repeats_per_context": 2,
    "workers": 4,
    "seed": 20260926,
}


def truncate(text: str, max_tokens: int) -> str:
    if count_tokens(text) <= max_tokens:
        return text
    _ids, offsets = encode_offsets(text)
    return text[: offsets[max_tokens - 1][1]]


_CHOICES = re.compile(r"\[([^\]]+)\]")
_EMPTY_CASE = re.compile(r"leave (?:it |this )?(?:empty|blank)|if not applicable|otherwise (?:null|empty)", re.I)
_ITEM = re.compile(r"'([^']+)'|\"([^\"]+)\"")


def declared_choices(description: str) -> tuple[tuple[str, ...], bool]:
    """Allowed values and whether several may be chosen, from the schema description."""

    text = description or ""
    match = _CHOICES.search(text)
    if not match or not re.search(r"\b(?:choose|select)\b", text.lower()):
        return (), False
    quoted = tuple(a or b for a, b in _ITEM.findall(match.group(1)))
    # Lists may be quoted (['Yes', 'No']) or bare ([Criminal Case, Civil Case]).
    items = quoted or tuple(part.strip() for part in match.group(1).split(","))
    multi = bool(re.search(r"one or more|all (?:the )?modalit|choose (?:all|several|multiple)", text.lower()))
    return tuple(i.strip() for i in items if i.strip()), multi


@dataclass(frozen=True)
class FieldSpec:
    """One extraction field under the benchmark's declared schema contract."""

    name: str
    value_type: str
    description: str
    nullable: bool = True
    choices: tuple[str, ...] = ()
    multi_choice: bool = False
    usage: str = ""  # how the reference workload uses the field (workload-informed shared reads)

    def line(self) -> str:
        kind = {"int": "integer", "float": "number"}.get(self.value_type, "text")
        many = self.value_type.startswith("multi") or self.multi_choice
        extra = " Multiple values separated by ' || '." if many else ""
        if self.choices:
            extra += f" Allowed values: {', '.join(self.choices)}."
        if not self.nullable:
            extra += " Never null: always give a value."
            if {c.lower() for c in self.choices} == {"yes", "no"}:
                extra += " Answer No unless the document indicates Yes."
        if self.usage:
            extra += f" Workload use: {self.usage}."
        return f"- {self.name} ({kind}): {self.description or self.name.replace('_', ' ')}.{extra}"


def conform(value: Any, field: FieldSpec) -> Any:
    """Validate a raw value against the declared domain; out-of-domain parts are dropped."""

    from quwarts.core.router.comparator import as_text, is_null

    if is_null(value):
        return None
    if not field.choices:
        return value
    lookup = {c.lower(): c for c in field.choices}
    parts = [p.strip() for p in as_text(value).split("||")] if field.multi_choice or field.value_type.startswith("multi") else [as_text(value).strip()]
    kept = []
    for part in parts:
        key = part.lower().strip(" .")
        match = lookup.get(key) or next((c for k, c in lookup.items() if key.startswith(k + " ") or key.startswith(k + ",")), None)
        if match and match not in kept:
            kept.append(match)
    if not kept:
        return None
    return " || ".join(kept) if len(kept) > 1 or field.multi_choice else kept[0]


_COUNT = re.compile(r"\b(?:number of|count of|how many)\b", re.I)
_ZERO_IF_NONE = re.compile(r"\b0 if (?:none|no|not)\b", re.I)


def absence_value(field: FieldSpec) -> Any:
    """The value a never-null field takes when the document says nothing about it.

    Only cases the schema itself declares: a never-null Yes/No field (absence
    means No), a description that states "0 if none", and a never-null count
    (absence means 0). Every other
    never-null field has no declared absence value and stays null (a recorded
    contract violation).
    """

    if field.nullable:
        return None
    if {c.lower() for c in field.choices} == {"yes", "no"}:
        return next(c for c in field.choices if c.lower() == "no")
    if _ZERO_IF_NONE.search(field.description or ""):
        return 0  # the description declares it ("1 if yes, 0 if none"; "use 0 if none")
    if field.value_type == "int" and _COUNT.search(field.description or ""):
        return 0
    return None


def complete(value: Any, field: FieldSpec) -> Any:
    """Conform to the declared domain, then apply the declared absence value."""

    value = conform(value, field)
    return absence_value(field) if value is None else value


def field_specs(spec: CorpusSpec, needs: list[Need], sql_numeric: set[str]) -> dict[str, FieldSpec]:
    """Fields as the SQL workload defines them: name and SQL-derived type, nothing else.

    The benchmark's attribute files (descriptions, allowed values, nullability) are not a
    system input (RULES.md). Without them every field is nullable and has no declared
    domain, so ``conform`` and ``absence_value`` are no-ops.
    """

    out: dict[str, FieldSpec] = {}
    for need in needs:
        value_type = "float" if need.qualified in sql_numeric else "str"
        out[need.qualified] = FieldSpec(need.attribute, value_type, "")
    return out


def protocol_field_specs(spec: CorpusSpec, needs: list[Need]) -> dict[str, FieldSpec]:
    """Fields under the benchmark's published protocol: each needed column's description, value
    type, nullability and declared allowed values come from the benchmark attribute file, as for
    every system the benchmark evaluates. Which columns are read, and how the workload uses them
    (the usage phrase added by the caller), still comes from the SQL workload."""

    attrs = spec.benchmark_attribute_descriptions(purpose="protocol")
    out: dict[str, FieldSpec] = {}
    for need in needs:
        record = attrs.get(spec.table(need.table).attributes_key, {}).get(need.attribute, {})
        description = str(record.get("description") or "")
        raw_type = str(record.get("value_type") or "str")
        value_type = raw_type if raw_type in ("int", "float") or raw_type.startswith("multi") else "str"
        choices, multi = declared_choices(description)
        if choices and not all(c.replace(".", "", 1).lstrip("-").isdigit() for c in choices):
            value_type = "str"  # a declared label set outranks the value type (e.g. Yes/No typed int)
        out[need.qualified] = FieldSpec(need.attribute, value_type, description,
                                        bool(record.get("is_nullable", True)), choices, multi)
    return out


def render_prompt(document: str, fields: list[FieldSpec], sql: str | None) -> str:
    head = "Extract the following fields about the single entity described in the document.\n"
    if sql:
        head += (
            "The fields are inputs to the SQL query below. Extract each field as that query intends it.\n"
            "Do not answer the query. Do not copy SQL constants unless the document supports them.\n"
        )
    if any(f.choices or not f.nullable for f in fields):
        head += "Follow each field's allowed values. Use null only for a field not marked 'Never null' that the document does not state.\n\n"
    else:
        head += "Use null when the document does not state a field.\n\n"
    body = f"DOCUMENT:\n{document}\n\n"
    if sql:
        body += f"SQL context:\n{sql}\n\n"
    body += "FIELDS:\n" + "\n".join(f.line() for f in fields) + "\n\n"
    body += 'Return JSON with this shape and no other keys: {"fields": {"<field>": <value or null>}}'
    return head + body


@dataclass
class Observations:
    """reads[(table, doc)][context] = list of field dicts (one per repeat)."""

    reads: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(list)))

    def add(self, table: str, doc: str, context: str, fields: dict[str, Any]) -> None:
        self.reads[(table, doc)][context].append(fields)

    def to_json(self) -> dict[str, Any]:
        return {f"{t}|{d}": {c: v for c, v in ctx.items()} for (t, d), ctx in self.reads.items()}

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "Observations":
        obs = cls()
        for key, ctx in payload.items():
            table, doc = key.split("|", 1)
            for context, rows in ctx.items():
                for row in rows:
                    obs.add(table, doc, context, row)
        return obs


def contexts_by_table(needs: list[Need]) -> dict[str, dict[str, list[Need]]]:
    """``{table: {context: needs read under it}}``; the canonical context serves every attribute."""

    out: dict[str, dict[str, list[Need]]] = defaultdict(lambda: defaultdict(list))
    for need in needs:
        out[need.table][need.query_id].append(need)
    for table, ctx in out.items():
        attrs = {}
        for items in ctx.values():
            for need in items:
                attrs.setdefault(need.attribute, need)
        ctx[CANONICAL] = list(attrs.values())
    return {t: dict(c) for t, c in out.items()}


class PairCounter:
    """Counts paired observations (consumer need, provider context) and repeats per context."""

    def __init__(self, needs: list[Need]):
        self.needs = needs
        self.by_attr: dict[str, list[Need]] = defaultdict(list)
        for need in needs:
            self.by_attr[need.qualified].append(need)
        self.pairs: dict[tuple[str, str], int] = defaultdict(int)
        self.repeats: dict[tuple[str, str], int] = defaultdict(int)  # (table, context) -> repeat reads

    def reads_attribute(self, table: str, context: str, qualified: str) -> bool:
        if context == CANONICAL:
            return qualified.split(".", 1)[0] == table
        return any(n.query_id == context for n in self.by_attr[qualified])

    def created(self, table: str, context: str, done: dict[str, list]) -> list[tuple[str, str, float]]:
        """Pairs (consumer key, provider context, weight) that one new read would create."""

        out = []
        mine = {n.qualified for n in self.needs if n.table == table and (n.query_id == context or context == CANONICAL)}
        for qualified in mine:
            for need in self.by_attr[qualified]:
                if need.query_id == context:
                    # This read's own need gains a provider for every other context already read
                    # here that also reads this attribute.
                    for other in done:
                        if other != context and self.reads_attribute(table, other, qualified):
                            out.append((need.key, other, need.weight))
                elif need.query_id in done:
                    # Needs already read on this doc gain this read as a provider.
                    out.append((need.key, context, need.weight))
        return out

    def record(self, table: str, context: str, done: dict[str, list]) -> None:
        if context in done:
            # A repeat measures noise; it adds no new document pair.
            self.repeats[(table, context)] += 1
            return
        for key, provider, _w in self.created(table, context, done):
            self.pairs[(key, provider)] += 1


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_context_probe(
    spec: CorpusSpec,
    needs: list[Need],
    queries: dict[str, str],
    doc_tokens: dict[str, dict[str, int]],
    fields: dict[str, FieldSpec],
    caller: BudgetedCaller,
    budget: int,
    journal: Path | None = None,
) -> dict[str, Any]:
    window = int(V3["window_tokens"])
    overhead = int(V3["call_overhead_tokens"])
    ctx_by_table = contexts_by_table(needs)
    counter = PairCounter(needs)
    obs = Observations()
    start = caller.ledger.spent
    exhausted = False

    pools: dict[str, list[str]] = {}
    texts: dict[tuple[str, str], str] = {}
    for table in ctx_by_table:
        paths = list_documents(spec.table(table))
        pool = length_stratified_sample(paths, doc_tokens[table], int(V3["pool_docs_per_table"]), f"v3:{table}")
        pools[table] = [path.name for path in pool]
        for path in pool:
            texts[(table, path.name)] = truncate(read_document(path), window)

    def read_cost(table: str, doc: str) -> int:
        return min(doc_tokens[table][doc], window) + overhead

    def utility(table: str, doc: str, context: str) -> float:
        done = obs.reads.get((table, doc), {})
        repeats = counter.repeats[(table, context)]
        gain = 0.0
        if context in done:
            # A repeat is worth it only until the noise floor has its quota.
            planned = planned_repeats[(table, context)]
            if repeats + planned >= int(V3["noise_repeats_per_context"]) or len(done[context]) > 1:
                return 0.0
            gain = sum(n.weight for n in ctx_by_table[table][context])
            return gain / read_cost(table, doc)
        for key, provider, weight in counter.created(table, context, done):
            gain += weight / (1 + counter.pairs[(key, provider)])
        if not done and context == CANONICAL:
            gain += 1e-6  # open a document with the read every later read can pair against
        return gain / read_cost(table, doc)

    def execute(action: tuple[str, str, str]) -> tuple[tuple[str, str, str], dict[str, Any] | None, str, str]:
        table, doc, context = action
        items = ctx_by_table[table][context]
        specs = [fields[n.qualified] for n in items]
        prompt = render_prompt(texts[(table, doc)], specs, None if context == CANONICAL else queries[context])
        try:
            text = caller.complete(prompt, "router_v3_probe", system=SYSTEM, table=table, doc=doc, context=context)
        except BudgetExhausted:
            return action, None, prompt, ""
        return action, parse_fields(text, [f.name for f in specs]), prompt, text

    def log(row: dict[str, Any]) -> None:
        if journal is None:
            return
        journal.parent.mkdir(parents=True, exist_ok=True)
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")

    # Budget share per table in proportion to its need weight.
    total_w = sum(n.weight for n in needs) or 1.0
    table_budget = {t: budget * sum(n.weight for n in needs if n.table == t) / total_w for t in ctx_by_table}
    table_spent: dict[str, float] = defaultdict(float)
    workers = int(V3["workers"])

    planned_repeats: dict[tuple[str, str], int] = defaultdict(int)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while not exhausted:
            planned_repeats.clear()
            candidates = []
            for table, contexts in ctx_by_table.items():
                for doc in pools[table]:
                    cost = read_cost(table, doc)
                    if table_spent[table] + cost > table_budget[table]:
                        continue
                    for context in contexts:
                        u = utility(table, doc, context)
                        if u > 0:
                            candidates.append((u, table, doc, context))
            if not candidates:
                break
            candidates.sort(key=lambda row: (-row[0], row[1], row[2], row[3]))
            batch, used_docs = [], set()
            for _u, table, doc, context in candidates:
                if (table, doc) in used_docs:
                    continue  # one read per document per batch keeps pairing decisions current
                if context in obs.reads.get((table, doc), {}):
                    quota = int(V3["noise_repeats_per_context"])
                    if counter.repeats[(table, context)] + planned_repeats[(table, context)] >= quota:
                        continue
                    planned_repeats[(table, context)] += 1
                batch.append((table, doc, context))
                used_docs.add((table, doc))
                if len(batch) == workers:
                    break
            for action, parsed, prompt, text in pool.map(execute, batch):
                table, doc, context = action
                if parsed is None:
                    exhausted = True
                    continue
                spent = caller.ledger.records[-1].tokens if caller.ledger.records else 0
                table_spent[table] += read_cost(table, doc)
                done = obs.reads.get((table, doc), {})
                counter.record(table, context, done)
                obs.add(table, doc, context, parsed)
                log({"table": table, "doc": doc, "context": context, "prompt_sha": _sha(prompt),
                     "prompt": prompt, "response": text, "tokens": spent})
    return {
        "budget": budget,
        "spent": caller.ledger.spent - start,
        "exhausted": exhausted,
        "pools": pools,
        "observations": obs.to_json(),
        "pair_counts": {f"{k}<-{p}": n for (k, p), n in sorted(counter.pairs.items())},
    }

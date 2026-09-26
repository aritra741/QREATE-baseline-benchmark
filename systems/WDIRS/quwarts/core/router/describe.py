"""Attribute descriptions generated from the reference workload (and corpus excerpts).

The benchmark's attribute files are not a system input. What the system does have is the
SQL workload, which shows how every column is used, and the corpus, which may be sampled.
For each attribute this module gives Qwen:

* every input query that uses it (the SQL is the only statement of intent there is),
* its roles and the values the workload compares it with,
* a few short passages from sampled documents that best match the attribute's name,

and asks for a one-paragraph extraction description: what the column means, its value
format, and what to output when a document does not mention it. The description is
journaled with its prompt and frozen before any extraction. A generated description that
contains attribute-file text is rejected (it cannot, since those files are never read;
the check makes that auditable).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from quwarts.core.corpus_probe.context import exhaustive_chunks
from quwarts.core.ledger import BudgetedCaller
from quwarts.core.router.corpus_features import deterministic_sample, list_documents, read_document
from quwarts.core.router.probes import parse_fields
from quwarts.core.router.registry import CorpusSpec
from quwarts.core.router.workload_features import AttributeUse, usage_phrase

EXCERPT_DOCS = 6
EXCERPTS_PER_ATTRIBUTE = 3
EXCERPT_TOKENS = 220
MAX_QUERIES = 12
SYSTEM = "You document database columns precisely. Return JSON."


def _terms(name: str) -> list[str]:
    return [t for t in re.split(r"[_\W]+", name.lower()) if len(t) > 2]


def excerpts(spec: CorpusSpec, table: str, attribute: str) -> list[str]:
    """Short passages from sampled documents that mention the attribute's name terms."""

    paths = deterministic_sample(list_documents(spec.table(table)), EXCERPT_DOCS, f"describe:{table}")
    terms = _terms(attribute)
    scored = []
    for path in paths:
        for chunk in exhaustive_chunks(read_document(path), EXCERPT_TOKENS):
            text = chunk["text"].lower()
            hits = sum(text.count(t) for t in terms)
            if hits:
                scored.append((hits, path.name, chunk["index"], chunk["text"].strip()))
    scored.sort(key=lambda row: (-row[0], row[1], row[2]))
    out, seen_docs = [], set()
    for _hits, doc, _index, text in scored:
        if doc in seen_docs:
            continue
        seen_docs.add(doc)
        out.append(text)
        if len(out) == EXCERPTS_PER_ATTRIBUTE:
            break
    return out


def sql_facts(use: AttributeUse, queries: dict[str, str]) -> dict[str, list[str]]:
    """Deterministic facts about one column from the SQL: direct comparisons, aggregates,
    stored values it is compared with, and CASE output labels (which are not stored values)."""

    import sqlglot
    from sqlglot import exp

    comparisons, aggregates, stored, outputs = set(), set(), set(), set()
    ops = {exp.EQ: "=", exp.NEQ: "!=", exp.GT: ">", exp.GTE: ">=", exp.LT: "<", exp.LTE: "<="}
    for qid in use.query_ids:
        if qid not in queries:
            continue
        tree = sqlglot.parse_one(queries[qid], read="sqlite")
        for node in tree.find_all(*ops, exp.In, exp.Like, exp.Is):
            cols = [c for c in node.find_all(exp.Column)]
            if len(cols) != 1 or cols[0].name != use.name:
                continue
            lits = [l for l in node.find_all(exp.Literal)]
            if isinstance(node, exp.In):
                vals = [l.sql() for l in lits]
                comparisons.add(f"{use.name} IN ({', '.join(vals)})")
            elif isinstance(node, exp.Like):
                comparisons.add(f"{use.name} LIKE {lits[0].sql()}" if lits else "")
            elif isinstance(node, exp.Is):
                comparisons.add(f"{use.name} IS NULL / IS NOT NULL")
            elif lits:
                comparisons.add(f"{use.name} {ops[type(node)]} {lits[0].sql()}")
            stored.update(l.this for l in lits if l.is_string and l.this.strip())
        for agg in tree.find_all(exp.AggFunc):
            if isinstance(agg.this, exp.Column) and agg.this.name == use.name:
                aggregates.add(f"{agg.key.upper()}({use.name})")
        for case in tree.find_all(exp.Case):
            refs = any(c.name == use.name for c in case.find_all(exp.Column))
            if refs:
                for branch in case.args.get("ifs") or []:
                    if isinstance(branch.args.get("true"), exp.Literal) and branch.args["true"].is_string:
                        outputs.add(branch.args["true"].this)
                default = case.args.get("default")
                if isinstance(default, exp.Literal) and default.is_string:
                    outputs.add(default.this)
    outputs -= stored
    return {"comparisons": sorted(c for c in comparisons if c), "aggregates": sorted(aggregates),
            "stored_values": sorted(stored), "case_outputs": sorted(outputs)}


def describe_prompt_v2(use: AttributeUse, queries: dict[str, str], passages: list[str]) -> str:
    facts = sql_facts(use, queries)
    sqls = [queries[q] for q in use.query_ids if q in queries][:MAX_QUERIES]
    lines = [
        f"A table named `{use.table}` has a column `{use.name}`. Its values will be extracted from one "
        "document per row with a language model. Write the instruction that tells the extractor what "
        "to put in this column.",
        "",
        "Facts about the column, derived from the SQL workload:",
        f"- Direct comparisons: {'; '.join(facts['comparisons']) or 'none'}",
        f"- Aggregates applied to it: {', '.join(facts['aggregates']) or 'none'}",
        f"- Stored values it is compared with: {', '.join(repr(v) for v in facts['stored_values']) or 'none'}",
        f"- Labels produced by CASE expressions (query outputs, NOT stored values): "
        f"{', '.join(repr(v) for v in facts['case_outputs']) or 'none'}",
        "",
        "Read the facts literally:",
        "- Compared only with the numbers 0 and 1: a 0/1 flag. Say what 1 means, given the column name.",
        "- Averaged, summed, or compared with other numbers: a number. Say what quantity it counts or measures,",
        "  consistent with the compared numbers (a column compared with >= 8 and averaged is a small count, not an ID).",
        "- Compared with stored string values: those strings are real values; others may exist.",
        "- CASE output labels are never stored values; never tell the extractor to output them.",
        "",
        "The queries:",
        *[f"  {i + 1}. {sql}" for i, sql in enumerate(sqls)],
    ]
    if passages:
        lines += ["", "Passages from documents in the corpus (the column may or may not appear in them):"]
        lines += [f"  [{i + 1}] {p[:900]}" for i, p in enumerate(passages)]
    lines += [
        "",
        'Return JSON: {"meaning": "<one sentence>", "format": "<value format>", '
        '"if_absent": "<null, or 0 for a flag or count that the document does not mention>"}',
    ]
    return "\n".join(lines)


def describe_prompt(use: AttributeUse, queries: dict[str, str], passages: list[str]) -> str:
    sqls = [queries[q] for q in use.query_ids if q in queries][:MAX_QUERIES]
    lines = [
        f"A table named `{use.table}` has a column `{use.name}`. Its values will be extracted from one "
        "document per row with a language model. Write the instruction that tells the extractor what "
        "to put in this column.",
        "",
        "How the SQL workload uses the column:",
        *[f"  {i + 1}. {sql}" for i, sql in enumerate(sqls)],
        "",
        f"Summary of its use: {usage_phrase(use) or 'selected as is'}.",
    ]
    if use.literals:
        lines.append("Values the workload compares it with: " + ", ".join(repr(v) for v in use.literals[:20]) + ".")
    if passages:
        lines += ["", "Passages from documents in the corpus (the column may or may not appear in them):"]
        lines += [f"  [{i + 1}] {p[:900]}" for i, p in enumerate(passages)]
    lines += [
        "",
        "Infer the column's meaning from how the queries use it (types, comparisons, aggregations,",
        "compared values) and from the passages. Do not invent facts about a specific document.",
        'Return JSON: {"meaning": "<one sentence>", "format": "<value format, e.g. integer count, '
        '0/1 flag, four-digit year, one of the compared labels, free text>", '
        '"if_absent": "<what to output when a document does not mention it, or null>"}',
    ]
    return "\n".join(lines)


def attribute_file_fragments(spec: CorpusSpec) -> list[str]:
    frags = []
    for key_attrs in spec.benchmark_attribute_descriptions(purpose="audit").values():
        for record in key_attrs.values():
            text = str(record.get("description") or "")
            frags.extend(text[i:i + 30] for i in range(0, max(1, len(text) - 30), 15) if len(text) >= 30)
    return frags


def generate_descriptions(
    spec: CorpusSpec,
    uses: list[AttributeUse],
    queries: dict[str, str],
    caller: BudgetedCaller,
    journal: Path,
    version: int = 2,
) -> dict[str, dict[str, Any]]:
    journal.parent.mkdir(parents=True, exist_ok=True)
    frags = attribute_file_fragments(spec)
    out: dict[str, dict[str, Any]] = {}
    for use in sorted(uses, key=lambda u: u.qualified):
        passages = excerpts(spec, use.table, use.name)
        prompt = (describe_prompt_v2 if version == 2 else describe_prompt)(use, queries, passages)
        text = caller.complete(prompt, "describe_attribute", system=SYSTEM, attribute=use.qualified)
        parsed = parse_fields(text, ["meaning", "format", "if_absent"])
        record = {k: (str(parsed.get(k)).strip() if parsed.get(k) not in (None, "") else None)
                  for k in ("meaning", "format", "if_absent")}
        rendered = description_text(record)
        leaked = [f for f in frags if f in rendered]
        if leaked:
            raise RuntimeError(f"{use.qualified}: generated description contains attribute-file text {leaked[:1]}")
        out[use.qualified] = {**record, "description": rendered}
        with journal.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"attribute": use.qualified, "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest(),
                                     "prompt": prompt, "response": text, "record": out[use.qualified],
                                     "tokens": caller.ledger.records[-1].tokens}, ensure_ascii=False) + "\n")
    return out


def description_text(record: dict[str, Any]) -> str:
    parts = []
    if record.get("meaning"):
        parts.append(record["meaning"].rstrip("."))
    if record.get("format"):
        parts.append(f"Format: {record['format'].rstrip('.')}")
    if record.get("if_absent"):
        parts.append(f"If the document does not mention it: {record['if_absent'].rstrip('.')}")
    return ". ".join(parts)


def mentions_case_label(text: str, facts: dict[str, list[str]]) -> list[str]:
    """CASE-only labels mentioned in ``text``, after masking real stored values
    (so 'Others' or 'Administrative Case' do not count as 'Other' or 'Administrative')."""

    masked = text
    for value in sorted(facts.get("stored_values", []), key=len, reverse=True):
        masked = re.sub(re.escape(value), " ", masked, flags=re.I)
    hits = []
    for label in facts.get("case_outputs", []):
        if re.search(r"(?<![\w])" + re.escape(label) + r"(?![\w])", masked, flags=re.I):
            hits.append(label)
    return hits


def describe_prompt_v3(use: AttributeUse, queries: dict[str, str], passages: list[str]) -> str:
    facts = sql_facts(use, queries)
    forbidden = facts["case_outputs"]
    extra = [
        "",
        "Constraints on your answer:",
        "- Never mention these labels anywhere; they are produced by queries and are never stored: "
        + (", ".join(repr(v) for v in forbidden) if forbidden else "(none)"),
        "- if_absent is null unless the column is a 0/1 flag or a count, in which case it is 0.",
    ]
    return describe_prompt_v2(use, queries, passages) + "\n".join(extra)


def generate_v3(spec: CorpusSpec, uses: list[AttributeUse], queries: dict[str, str], caller: BudgetedCaller,
                journal: Path, attempts: int = 3) -> dict[str, dict[str, Any]]:
    """v2 prompt plus explicit constraints; each answer is validated and retried if it breaks them.
    An attribute whose answers never pass gets no description (the extractor sees its name only)."""

    frags = attribute_file_fragments(spec)
    out: dict[str, dict[str, Any]] = {}
    for use in sorted(uses, key=lambda u: u.qualified):
        facts = sql_facts(use, queries)
        passages = excerpts(spec, use.table, use.name)
        prompt = describe_prompt_v3(use, queries, passages)
        accepted = None
        for attempt in range(attempts):
            text = caller.complete(prompt + ("" if attempt == 0 else f"\n(Attempt {attempt + 1}.)"),
                                   "describe_attribute_v3", system=SYSTEM, attribute=use.qualified)
            parsed = parse_fields(text, ["meaning", "format", "if_absent"])
            record = {k: (str(parsed.get(k)).strip() if parsed.get(k) not in (None, "", "null") else None)
                      for k in ("meaning", "format", "if_absent")}
            absent = (record.get("if_absent") or "").strip("'\" ")
            # 0 only where the workload itself compares the column with 0 or 1 (flags, counts);
            # never for years or amounts the SQL compares with other numbers.
            zero_ok = any(re.search(r"(?:=|!=|<|>|<=|>=)\s*[01](?:\.0)?$", c) for c in facts["comparisons"])
            record["if_absent"] = "0" if absent in ("0", "0.0") and use.numeric and zero_ok else None
            rendered = description_text(record)
            violations = mentions_case_label(rendered, facts)
            with journal.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"attribute": use.qualified, "attempt": attempt, "prompt": prompt,
                                         "response": text, "violations": violations,
                                         "tokens": caller.ledger.records[-1].tokens}, ensure_ascii=False) + "\n")
            if [f for f in frags if f in rendered]:
                raise RuntimeError(f"{use.qualified}: attribute-file text in generated description")
            if not violations and record.get("meaning"):
                accepted = {**record, "description": rendered}
                break
        if accepted:
            out[use.qualified] = accepted
    return out

"""Ground-truth-free workload intent analysis.

Natural-language queries are converted into a schema-independent requirement
IR. SQL input remains supported for diagnostics and migration experiments.
The analyzer never reads UDA-Bench tables or attributes metadata.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from spp.budget_ledger import GlobalBudgetLedger
from spp.budgeted_llm import BudgetedLLMClient
from spp.spec import QueryRequirement

try:
    import sqlglot
    from sqlglot import exp
except ImportError:  # pragma: no cover - surfaced only in minimal deployments
    sqlglot = None
    exp = None


_AGGREGATES = {
    "count": "count",
    "how many": "count",
    "average": "avg",
    "avg": "avg",
    "sum": "sum",
    "total": "sum",
    "minimum": "min",
    "smallest": "min",
    "maximum": "max",
    "largest": "max",
}
_UNIT_RE = re.compile(
    r"\b(usd|dollars?|euros?|pounds?|kg|kilograms?|g|grams?|km|kilometers?|"
    r"miles?|meters?|percent|%)\b",
    re.IGNORECASE,
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "did",
    "do", "does", "for", "from", "had", "has", "have", "how", "in", "is",
    "it", "of", "on", "or", "that", "the", "their", "to", "was", "were",
    "what", "when", "which", "who", "with",
}


@dataclass(frozen=True)
class WorkloadIntent:
    requirements: Tuple[QueryRequirement, ...]
    entity_frequency: Mapping[str, int]
    attribute_frequency: Mapping[str, int]
    operator_frequency: Mapping[str, int]

    @property
    def has_joins(self) -> bool:
        return any(r.relationships for r in self.requirements)

    @property
    def has_units(self) -> bool:
        return any(r.units for r in self.requirements)

    @property
    def has_numeric_operations(self) -> bool:
        numeric_ops = {"count", "sum", "avg", "min", "max", "range"}
        return any(numeric_ops.intersection(r.operators) for r in self.requirements)

    def query_ids(self) -> Tuple[str, ...]:
        return tuple(r.query_id for r in self.requirements)


def _is_sql(text: str) -> bool:
    return bool(re.match(r"^\s*(select|with)\b", text, re.IGNORECASE))


def _sql_requirement(query_id: str, sql: str) -> QueryRequirement:
    if sqlglot is None or exp is None:
        raise RuntimeError("sqlglot is required to analyze SQL workloads")
    tree = sqlglot.parse_one(sql)
    aliases: Dict[str, str] = {}
    entities: List[str] = []
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name not in entities:
            entities.append(name)
        aliases[name] = name
        aliases[(table.alias_or_name or name).lower()] = name

    attributes: List[str] = []
    attribute_bindings: List[Tuple[str, str]] = []
    for column in tree.find_all(exp.Column):
        name = column.name.lower()
        if name not in attributes:
            attributes.append(name)
        table_name = aliases.get((column.table or "").lower())
        if table_name is None and len(entities) == 1:
            table_name = entities[0]
        binding = (table_name, name) if table_name else None
        if binding and binding not in attribute_bindings:
            attribute_bindings.append(binding)

    relationships: List[Tuple[str, str, str]] = []
    for join in tree.find_all(exp.Join):
        on_expr = join.args.get("on")
        if on_expr is None:
            continue
        for equality in on_expr.find_all(exp.EQ):
            left, right = equality.left, equality.right
            if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                continue
            fallback_table = entities[0] if entities else "record"
            left_raw = (left.table or fallback_table).lower()
            right_raw = (right.table or fallback_table).lower()
            left_table = aliases.get(left_raw, left_raw)
            right_table = aliases.get(right_raw, right_raw)
            relationships.append(
                (left_table, f"{left.name.lower()}={right.name.lower()}", right_table)
            )

    operators: List[str] = []
    op_types = (
        (exp.Count, "count"),
        (exp.Sum, "sum"),
        (exp.Avg, "avg"),
        (exp.Min, "min"),
        (exp.Max, "max"),
        (exp.Group, "group_by"),
        (exp.Where, "filter"),
        (exp.Join, "join"),
    )
    for node_type, label in op_types:
        if next(tree.find_all(node_type), None) is not None:
            operators.append(label)

    return QueryRequirement(
        query_id=query_id,
        text=sql,
        entities=tuple(entities),
        attributes=tuple(attributes),
        attribute_bindings=tuple(attribute_bindings),
        relationships=tuple(relationships),
        operators=tuple(operators),
        units=tuple(sorted({m.group(1).lower() for m in _UNIT_RE.finditer(sql)})),
    )


def _heuristic_nl_requirement(query_id: str, text: str) -> QueryRequirement:
    lowered = text.lower()
    operators: List[str] = []
    for phrase, operator in _AGGREGATES.items():
        if phrase in lowered and operator not in operators:
            operators.append(operator)
    if any(token in lowered for token in (" where ", " whose ", " with ", " before ", " after ")):
        operators.append("filter")
    if any(token in lowered for token in (" between ", " compared ", " per ", " each ")):
        operators.append("group_by")
    if any(token in lowered for token in (" related ", " owned by ", " belongs to ", " joined ")):
        operators.append("join")

    content_words = [
        word.lower()
        for word in _WORD_RE.findall(text)
        if word.lower() not in _STOPWORDS and len(word) > 2
    ]
    # Without an LLM we deliberately produce a conservative generic entity and
    # retain content terms as candidate attributes. This is auditable and never
    # pretends to have inferred a domain schema with high confidence.
    attributes = tuple(dict.fromkeys(content_words))
    return QueryRequirement(
        query_id=query_id,
        text=text,
        entities=("record",),
        attributes=attributes,
        operators=tuple(dict.fromkeys(operators)),
        units=tuple(sorted({m.group(1).lower() for m in _UNIT_RE.finditer(text)})),
    )


def _parse_llm_payload(
    payload: str, queries_by_id: Mapping[str, str]
) -> List[QueryRequirement]:
    start, end = payload.find("["), payload.rfind("]")
    if start < 0 or end < start:
        raise ValueError("intent analyzer did not return a JSON array")
    rows = json.loads(payload[start : end + 1])
    if not isinstance(rows, list):
        raise ValueError("intent payload must be a list")
    requirements: List[QueryRequirement] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        query_id = str(row.get("query_id", ""))
        if query_id not in queries_by_id or query_id in seen:
            continue
        seen.add(query_id)
        def list_field(name: str) -> list:
            value = row.get(name)
            return list(value) if isinstance(value, (list, tuple)) else []

        relationships = []
        for rel in list_field("relationships"):
            if isinstance(rel, Mapping):
                parsed = (
                    str(rel.get("left", "")).lower(),
                    str(rel.get("relation", "")).lower(),
                    str(rel.get("right", "")).lower(),
                )
                if all(parsed):
                    relationships.append(parsed)
            elif isinstance(rel, (list, tuple)) and len(rel) == 3:
                parsed = tuple(str(v).lower() for v in rel)
                if all(parsed):
                    relationships.append(parsed)
        requirements.append(
            QueryRequirement(
                query_id=query_id,
                text=queries_by_id[query_id],
                entities=tuple(
                    dict.fromkeys(str(v).lower() for v in list_field("entities"))
                ),
                attributes=tuple(
                    dict.fromkeys(str(v).lower() for v in list_field("attributes"))
                ),
                attribute_bindings=tuple(
                    (str(v.get("entity", "")).lower(), str(v.get("attribute", "")).lower())
                    for v in list_field("attribute_bindings")
                    if isinstance(v, Mapping) and v.get("entity") and v.get("attribute")
                ),
                relationships=tuple(relationships),
                operators=tuple(
                    dict.fromkeys(str(v).lower() for v in list_field("operators"))
                ),
                units=tuple(
                    dict.fromkeys(str(v).lower() for v in list_field("units"))
                ),
            )
        )
    missing = set(queries_by_id) - seen
    requirements.extend(
        _heuristic_nl_requirement(query_id, queries_by_id[query_id])
        for query_id in sorted(missing)
    )
    return requirements


def analyze_workload(
    queries: Sequence[Mapping[str, Any] | str],
    *,
    llm_client: Optional[Any] = None,
) -> WorkloadIntent:
    """Analyze SQL or NL workload without reading any ground-truth artifact."""
    normalized: List[Tuple[str, str]] = []
    for index, query in enumerate(queries):
        if isinstance(query, str):
            normalized.append((f"q{index}", query))
        else:
            normalized.append(
                (
                    str(query.get("query_id", f"q{index}")),
                    str(query.get("text") or query.get("nl_query") or query.get("sql") or ""),
                )
            )
    if not normalized or any(not text.strip() for _, text in normalized):
        raise ValueError("workload queries must contain non-empty text")

    sql_requirements: Dict[str, QueryRequirement] = {}
    nl_queries: Dict[str, str] = {}
    for query_id, text in normalized:
        if _is_sql(text):
            sql_requirements[query_id] = _sql_requirement(query_id, text)
        else:
            nl_queries[query_id] = text

    nl_requirements: List[QueryRequirement]
    if nl_queries and llm_client is not None:
        prompt = (
            "Convert each analytical query into a schema-independent intent. "
            "Return ONLY a JSON array. Each item must contain query_id, entities, "
            "attributes, attribute_bindings (entity/attribute), relationships "
            "(left/relation/right), operators, and units. "
            "Use lowercase snake_case names and do not invent facts from any "
            "ground-truth table.\n\nQueries:\n"
            + json.dumps(
                [{"query_id": qid, "query": text} for qid, text in nl_queries.items()],
                indent=2,
            )
        )
        response = llm_client.generate(prompt, max_tokens=4096, temperature=0.0)
        nl_requirements = _parse_llm_payload(response, nl_queries)
    else:
        nl_requirements = [
            _heuristic_nl_requirement(query_id, text)
            for query_id, text in nl_queries.items()
        ]

    by_id = {**sql_requirements, **{r.query_id: r for r in nl_requirements}}
    ordered = tuple(by_id[query_id] for query_id, _ in normalized)
    return WorkloadIntent(
        requirements=ordered,
        entity_frequency=dict(Counter(v for r in ordered for v in r.entities)),
        attribute_frequency=dict(Counter(v for r in ordered for v in r.attributes)),
        operator_frequency=dict(Counter(v for r in ordered for v in r.operators)),
    )


def make_budgeted_intent_analyzer(llm_client: Any):
    """Adapt a WDIRS-compatible client to the system's analyzer callback."""

    def analyzer(
        queries: Sequence[Mapping[str, Any] | str],
        ledger: GlobalBudgetLedger,
    ) -> WorkloadIntent:
        budgeted = BudgetedLLMClient(
            llm_client, ledger, default_stage="workload_analysis"
        )
        return analyze_workload(queries, llm_client=budgeted)

    return analyzer

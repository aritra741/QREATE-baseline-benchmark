"""Control-variate survey execution for the 16 Legal queries at θ50.

Qwen returns one document's query contribution. The frozen WCCI database is the
full-corpus control variate. Benchmark gold stays unread until the hybrid bags
are frozen.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import math
import os
import random
import re
import sqlite3
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ROOT = Path("/Users/aritramazumder/Documents/UDA-Bench-main")
sys.path[:0] = [str(ROOT / "systems" / "WDIRS"), str(ROOT / "systems" / "docetl-main"), str(ROOT)]

_OPEN = builtins.open
_FROZEN = {"ok": False}
_BLOCK = (
    "ground_truth",
    "/gold/",
    "gold.json",
    "extract_fields.json",
    "pipeline_output.json",
    "query_results.json",
    "evaluation.json",
    "shared_reachability",
    "cost_aware_reachability",
    "diagnostic_scores",
    "evidence_card_aggregation",
    "quwarts_legal_expert_budget",
    "docetl_legal_case80/docetl_pipelines",
    "stage_a",
    "scores.json",
)
_ALLOW = (
    "query_manifest.json",
    "legal_attributes.json",
    "observables.json",
    "quwarts_legal_wcci_theta50/bags.json",
    "quwarts_legal_wcci_theta50/frozen.json",
    "quwarts_legal_wcci_theta50/sample_frozen.json",
    "quwarts_legal_wcci_theta50/journal.jsonl",
    "quwarts_legal_wcci_theta50/design_frozen.json",
    "quwarts_legal_wcci_theta50/ledger.json",
    "quwarts_legal_wcci_theta50/assignment_manifest.json",
    "quwarts_legal_wcci_theta50/scorer_frozen.json",
)


def _blocked(path: object) -> bool:
    if _FROZEN["ok"]:
        return False
    text = str(path).replace("\\", "/")
    lower = text.lower()
    if any(text.endswith(suffix) or suffix in text for suffix in _ALLOW):
        return False
    return any(fragment.lower() in lower for fragment in _BLOCK)


def _guard(path, *args, **kwargs):
    if _blocked(path):
        raise PermissionError(f"forbidden_before_freeze:{path}")
    return _OPEN(path, *args, **kwargs)


builtins.open = _guard

import sqlglot
from sqlglot import exp

from quwarts.core.ledger import BudgetExhausted, TokenLedger
from quwarts.core.llm.openrouter import load_env_file, make_caller
from quwarts.core.observable_sidecar import bag_hash
from quwarts.core.retrieve_extract.tokens import count_tokens, encode_offsets

MANIFEST = ROOT / "results" / "docetl_legal_case80" / "query_manifest.json"
WCCI_DB = ROOT / "results" / "quwarts_legal_wcci_theta50" / "legal_wcci.db"
WCCI_BAGS = ROOT / "results" / "quwarts_legal_wcci_theta50" / "bags.json"
WCCI_SAMPLE = ROOT / "results" / "quwarts_legal_wcci_theta50" / "sample_frozen.json"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
ATTRIBUTES = ROOT / "Query" / "Legal" / "Legal_attributes.json"
DOCS = ROOT / "source_data" / "Legal" / "legal_case"
OUT = ROOT / "results" / "quwarts_legal_survey_theta50"
WCCI_DB_HASH = "52a772cd04a1f8abe19d9ed73091779ef0593f6e681c4847095e3b2ce9936117"
WCCI_BAG_HASH = "3bf8f1764778ef5fb332a3d9179b70f3204e6f26afcfb3fdf901d1db35021615"
WCCI_SPENT = 1_639_733
THETA = 25_220_022
REMAINING = THETA - WCCI_SPENT
DOCETL_PRODUCT = 0.12350932750098194
WCCI_PRODUCT = 0.09594618648894966
SEED = 20260922
MODEL = "qwen/qwen-2.5-7b-instruct"

DESIGN: dict[str, Any] = {
    "name": "control-variate survey query execution",
    "model": MODEL,
    "seed": SEED,
    "theta_cumulative": THETA,
    "wcci_spent": WCCI_SPENT,
    "remaining_budget": REMAINING,
    "token_allocation": {
        "extraction": 16_000_000,
        "validation": 6_000_000,
        "reserve": 1_580_289,
        "optimization_tokens": 0,
    },
    "context_limit_tokens": 28000,
    "chunk_tokens": 4500,
    "max_exhaustive_chunks": 8,
    "extraction_max_tokens": 900,
    "validation_max_tokens": 400,
    "workers": 3,
    "sampling": {
        "design": "two independent Poisson waves",
        "wave0_target": 110,
        "wave0_floor": 0.025,
        "wave0_cap": 0.70,
        "wave1_target": 70,
        "wave1_cap": 0.55,
        "combination": "weight each wave's Horvitz-Thompson residual by its expected sample size",
        "nonresponse": "an unknown contribution is omitted; it is not coded as FALSE or zero",
    },
    "strata": [
        "document_length_decile",
        "wcci_support_prediction",
        "wcci_rare_group",
        "wcci_numeric_decile",
        "wcci_type_confidence",
        "candidate_density_quartile",
        "conflicting_candidate",
        "plumbing_wcci_disagreement",
        "section_or_table",
        "workload_label",
        "prior_probe_uncertainty",
        "singleton_group_member",
    ],
    "bundles": [
        ["legal_agg20:q3"],
        ["legal_filter20:q9", "legal_agg20:q11", "legal_filter20:q15"],
        ["legal_filter20:q7"],
        ["legal_groupby20:q14", "legal_filter20:q8", "legal_agg20:q13"],
        ["legal_agg20:q17", "legal_filter20:q11"],
        ["legal_multiagg20:q11"],
        ["legal_multiagg20:q18"],
        ["legal_multiagg20:q9"],
        ["legal_multiagg20:q4", "legal_agg20:q4", "legal_agg20:q14"],
    ],
    "bundle_limits": {"queries": 3, "attributes": 4, "numeric_outputs": 2, "documents_per_call": 1},
    "estimator": {
        "additive": "sum_i x_i + sum_sampled (y_i - x_i) / pi_i",
        "avg": "estimated numerator / estimated non-null denominator",
        "count_distinct": "unused; Chao unseen-mass plus HT identity indicators if a future query needs it; identity is __entity_id when the grain is the entity",
        "max_min": "certainty tail from WCCI extremes and top numeric candidates; validated value, else WCCI; never a scaled sample",
        "bootstrap_replicates": 24,
        "half_samples": 2,
        "variance": "Poisson: sum (1-pi) (residual/pi)^2",
    },
    "acceptance": {
        "min_effective_sample_size": 8,
        "min_known_responses": 20,
        "min_known_rate_among_wcci_support": 0.45,
        "count_relative": 0.25,
        "count_absolute": 2,
        "numeric_ci_relative": 0.50,
        "kept_group_min_count": 3,
        "min_change_relative": 0.02,
        "min_change_absolute": 1,
        "having_must_be_stable_at_both_ci_endpoints": True,
        "no_incomplete_context_absence": True,
        "query_local": True,
    },
    "adaptive_priority": "workload_weight * variance * sql_amplification * nonzero_residual_probability / estimated_call_cost",
    "stopping": "stop a query when its acceptance gate already passes, when expected variance reduction is below 2 percent, or when the next complete call cannot be reserved",
    "fallback": "retain the frozen WCCI bag for any query that fails acceptance",
    "prompts": {
        "extraction_system": "You extract one document's contribution to a SQL group-by query. Return JSON only. Do not compute a corpus total, do not list other cases, and do not invent values that the document does not support.",
        "validation_system": "You check one proposed row contribution against cited evidence. Return JSON only. Decide accept, reject, or uncertain. Do not propose a replacement value.",
    },
}


def sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def same(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool) and not isinstance(right, bool):
        scale = max(1.0, abs(float(left)), abs(float(right)))
        return abs(float(left) - float(right)) <= 1e-8 * scale
    return str(left) == str(right)


def lit(node: exp.Expression) -> Any:
    if not isinstance(node, exp.Literal):
        raise ValueError(f"expected literal, got {type(node).__name__}")
    if node.is_string:
        return str(node.this)
    text = str(node.this)
    return float(text) if "." in text else int(text)


def compile_predicate(node: exp.Expression) -> dict[str, Any]:
    if isinstance(node, exp.And):
        return {"op": "and", "args": [compile_predicate(node.this), compile_predicate(node.expression)]}
    if isinstance(node, exp.Not) and isinstance(node.this, exp.Is):
        return {"op": "not_null", "column": node.this.this.name}
    if isinstance(node, exp.Is):
        return {"op": "is_null", "column": node.this.name}
    if isinstance(node, (exp.EQ, exp.NEQ, exp.LT, exp.LTE, exp.GT, exp.GTE)):
        symbols = {exp.EQ: "=", exp.NEQ: "!=", exp.LT: "<", exp.LTE: "<=", exp.GT: ">", exp.GTE: ">="}
        column = node.this if isinstance(node.this, exp.Column) else node.expression
        value = node.expression if isinstance(node.this, exp.Column) else node.this
        return {"op": "compare", "column": column.name, "cmp": symbols[type(node)], "value": lit(value)}
    if isinstance(node, exp.In):
        return {"op": "in", "column": node.this.name, "values": [lit(item) for item in node.expressions]}
    if isinstance(node, exp.Between):
        return {"op": "between", "column": node.this.name, "low": lit(node.args["low"]), "high": lit(node.args["high"])}
    raise ValueError(f"unsupported predicate {type(node).__name__}: {node}")


def compile_value(node: exp.Expression | None) -> dict[str, Any]:
    if node is None:
        return {"op": "null"}
    if isinstance(node, exp.Literal):
        return {"op": "literal", "value": lit(node)}
    if isinstance(node, exp.Column):
        return {"op": "column", "column": node.name}
    if isinstance(node, exp.Case):
        return {
            "op": "case",
            "whens": [{"if": compile_predicate(item.this), "then": compile_value(item.args.get("true"))} for item in node.args.get("ifs") or []],
            "else": compile_value(node.args.get("default")),
        }
    if isinstance(node, exp.If):
        return {"op": "case", "whens": [{"if": compile_predicate(node.this), "then": compile_value(node.args.get("true"))}], "else": compile_value(node.args.get("false"))}
    raise ValueError(f"unsupported value {type(node).__name__}: {node}")


def compile_aggregate(node: exp.Expression, alias: str) -> dict[str, Any]:
    if isinstance(node, exp.Count):
        return {"alias": alias, "op": "count_star"}
    if isinstance(node, exp.Avg):
        return {"alias": alias, "op": "avg", "column": node.this.name}
    if isinstance(node, exp.Max):
        return {"alias": alias, "op": "max", "column": node.this.name}
    if isinstance(node, exp.Sum):
        inner = node.this
        if not isinstance(inner, exp.Case):
            raise ValueError(f"unsupported sum {inner}")
        return {"alias": alias, "op": "sum_case", "case": compile_value(inner)}
    raise ValueError(f"unsupported aggregate {type(node).__name__}")


def compile_query(query: dict[str, str]) -> dict[str, Any]:
    tree = sqlglot.parse_one(query["sql"])
    where = tree.args.get("where")
    predicate = compile_predicate(where.this) if where is not None else {"op": "true"}
    groups = []
    aggregates = []
    for expression in tree.expressions:
        alias = expression.alias
        node = expression.this if isinstance(expression, exp.Alias) else expression
        if isinstance(node, (exp.Count, exp.Avg, exp.Sum, exp.Max)):
            aggregates.append(compile_aggregate(node, alias or node.sql()))
        else:
            groups.append({"alias": alias or node.sql(), "expr": compile_value(node)})
    having = None
    having_node = tree.args.get("having")
    if having_node is not None:
        compare = having_node.this
        having = {"count_star_gte": int(lit(compare.expression))}
    support_sql = where.this.sql(dialect="sqlite") if where is not None else "1"
    atoms: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("op") in {"not_null", "compare", "in", "between", "column"} and node.get("column"):
                atoms.add(node["column"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(predicate)
    walk(groups)
    walk(aggregates)
    group_sql = []
    value_sql = []
    for expression in tree.expressions:
        node = expression.this if isinstance(expression, exp.Alias) else expression
        alias = expression.alias or node.sql(dialect="sqlite")
        if isinstance(node, exp.Sum):
            value_sql.append({"alias": alias, "sql": node.this.sql(dialect="sqlite")})
        elif isinstance(node, (exp.Avg, exp.Max)):
            value_sql.append({"alias": alias, "sql": node.this.sql(dialect="sqlite")})
        elif not isinstance(node, exp.Count):
            group_sql.append({"alias": alias, "sql": node.sql(dialect="sqlite")})
    return {
        "query_id": query["query_id"],
        "support_predicates": [predicate],
        "support_sql": support_sql,
        "group_sql": group_sql,
        "value_sql": value_sql,
        "columns": sorted({column.name for column in tree.find_all(exp.Column)}),
        "presence_atoms": sorted(atoms),
        "group_expression": groups,
        "aggregate_terms": aggregates,
        "having_expression": having,
        "distinct_identity": None,
    }


def truth(node: dict[str, Any], row: dict[str, Any], conn: sqlite3.Connection) -> bool | None:
    op = node["op"]
    if op == "true":
        return True
    if op == "and":
        values = [truth(item, row, conn) for item in node["args"]]
        if any(item is False for item in values):
            return False
        if any(item is None for item in values):
            return None
        return True
    if op == "not_null":
        return row.get(node["column"]) is not None
    if op == "is_null":
        return row.get(node["column"]) is None
    column = row.get(node["column"]) if "column" in node else None
    if op == "compare":
        if column is None:
            return None
        result = conn.execute(f"SELECT ? {node['cmp']} ?", (column, node["value"])).fetchone()[0]
        return None if result is None else bool(result)
    if op == "in":
        if column is None:
            return None
        marks = ", ".join("?" for _ in node["values"])
        result = conn.execute(f"SELECT ? IN ({marks})", (column, *node["values"])).fetchone()[0]
        return None if result is None else bool(result)
    if op == "between":
        if column is None:
            return None
        result = conn.execute("SELECT ? BETWEEN ? AND ?", (column, node["low"], node["high"])).fetchone()[0]
        return None if result is None else bool(result)
    raise ValueError(op)


def evaluate(node: dict[str, Any], row: dict[str, Any], conn: sqlite3.Connection) -> Any:
    op = node["op"]
    if op == "null":
        return None
    if op == "literal":
        return node["value"]
    if op == "column":
        return row.get(node["column"])
    if op == "case":
        for item in node["whens"]:
            if truth(item["if"], row, conn) is True:
                return evaluate(item["then"], row, conn)
        return evaluate(node["else"], row, conn)
    raise ValueError(op)


def case_labels(node: dict[str, Any]) -> list[Any]:
    labels = []
    if node.get("op") == "case":
        for item in node["whens"]:
            value = item["then"]
            if value.get("op") == "literal":
                labels.append(value["value"])
        default = node.get("else") or {}
        if default.get("op") == "literal":
            labels.append(default["value"])
    return labels


def row_contribution(spec: dict[str, Any], row: dict[str, Any], conn: sqlite3.Connection) -> dict[str, Any] | None:
    columns = sorted(set(spec.get("columns") or spec["presence_atoms"]) | {"doc_id"})
    conn.execute("DROP TABLE IF EXISTS one")
    declared = ", ".join(f'"{name}" TEXT' for name in columns)
    conn.execute(f"CREATE TABLE one ({declared})")
    conn.execute(
        f'INSERT INTO one VALUES ({", ".join("?" for _ in columns)})',
        [None if row.get(name) is None else str(row.get(name)) for name in columns],
    )
    supported = conn.execute(f"SELECT ({spec['support_sql']}) FROM one").fetchone()[0]
    if supported != 1:
        return None
    groups = {item["alias"]: conn.execute(f"SELECT ({item['sql']}) FROM one").fetchone()[0] for item in spec["group_sql"]}
    values = {item["alias"]: conn.execute(f"SELECT ({item['sql']}) FROM one").fetchone()[0] for item in spec["value_sql"]}
    return {"doc_id": row["doc_id"], "groups": groups, "values": values}


def materialize_bag(spec: dict[str, Any], contributions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    group_aliases = [item["alias"] for item in spec["group_expression"]]
    conn = sqlite3.connect(":memory:")
    columns = group_aliases + [term["alias"] for term in spec["aggregate_terms"] if term["op"] != "count_star"]
    declared = ", ".join(f'"{name}" TEXT' for name in columns)
    conn.execute(f'CREATE TABLE c ({declared})')
    if contributions and columns:
        marks = ", ".join("?" for _ in columns)
        payload = []
        for item in contributions:
            payload.append([None if item["groups"].get(name) is None else str(item["groups"].get(name)) for name in group_aliases] + [
                None if item["values"].get(term["alias"]) is None else str(item["values"].get(term["alias"]))
                for term in spec["aggregate_terms"] if term["op"] != "count_star"
            ])
        conn.executemany(f"INSERT INTO c VALUES ({marks})", payload)
    select = []
    for alias in group_aliases:
        select.append(f'"{alias}"')
    for term in spec["aggregate_terms"]:
        if term["op"] == "count_star":
            select.append(f'COUNT(*) AS "{term["alias"]}"')
        elif term["op"] == "avg":
            select.append(f'AVG("{term["alias"]}") AS "{term["alias"]}"')
        elif term["op"] == "sum_case":
            select.append(f'SUM("{term["alias"]}") AS "{term["alias"]}"')
        elif term["op"] == "max":
            select.append(f'MAX("{term["alias"]}") AS "{term["alias"]}"')
    group_sql = ", ".join(f'"{name}"' for name in group_aliases)
    having = ""
    if spec["having_expression"]:
        count_alias = next(term["alias"] for term in spec["aggregate_terms"] if term["op"] == "count_star")
        having = f' HAVING "{count_alias}" >= {int(spec["having_expression"]["count_star_gte"])}'
    sql = f'SELECT {", ".join(select)} FROM c GROUP BY {group_sql}{having}'
    cursor = conn.execute(sql)
    names = [item[0] for item in cursor.description]
    rows = [dict(zip(names, record)) for record in cursor.fetchall()]
    conn.close()
    return rows


def bag_equal(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> bool:
    def key(row: dict[str, Any]) -> str:
        return json.dumps(row, sort_keys=True, default=str)

    if len(left) != len(right):
        return False
    paired = defaultdict(list)
    for row in right:
        paired[key({name: None if value is None else value for name, value in row.items()})].append(row)
    used = defaultdict(int)
    for row in left:
        matches = [item for item in right if set(item) == set(row) and all(same(row[name], item[name]) for name in row)]
        if len(matches) <= used[key(row)]:
            return False
        used[key(row)] += 1
    return True


def load_rows(path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = [dict(row) for row in conn.execute("SELECT * FROM legal ORDER BY doc_id")]
    conn.close()
    return rows


def decile(values: dict[str, float]) -> dict[str, int]:
    ordered = sorted(values, key=lambda key: (values[key], key))
    width = max(1, len(ordered)) / 10
    return {key: min(10, int(index / width) + 1) for index, key in enumerate(ordered)}


def quartile(flags: dict[str, float]) -> dict[str, int]:
    ordered = sorted(flags, key=lambda key: (flags[key], key))
    width = max(1, len(ordered)) / 4
    return {key: min(4, int(index / width) + 1) for index, key in enumerate(ordered)}


def sql_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def wcci_query_contrib(spec: dict[str, Any], contribution: dict[str, Any] | None) -> dict[str, Any]:
    if contribution is None:
        return {"support": False, "groups": {}, "values": {}}
    return {"support": True, "groups": contribution["groups"], "values": contribution["values"]}


def typed_number(value: Any) -> int | None:
    number = sql_number(value)
    if number is None:
        return None
    if abs(number - round(number)) > 1e-8:
        return None
    return int(round(number))


def build_strata(docs: dict[str, str], wcci: dict[str, dict[str, Any]], plumbing: dict[str, dict[str, Any]], specs: list[dict[str, Any]], contributions: dict[str, dict[str, dict[str, Any] | None]], sample: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lengths = {doc: float(len(text)) for doc, text in docs.items()}
    length_decile = decile(lengths)
    roles = sample.get("roles") or {}
    label_re = re.compile(r"Company|Organization|Government|Dismissed|Approved|Civil Case|Administrative Case|Commercial Case|Criminal Case", re.I)
    year_re = re.compile(r"\b(19|20)\d{2}\b")
    act_re = re.compile(r"\bAct\s+(18|19|20)\d{2}\b")
    section_re = re.compile(r"\n\s*(section|schedule|orders|held)\b|\|", re.I)
    group_counts: dict[tuple[str, str], int] = defaultdict(int)
    members: dict[tuple[str, str], list[str]] = defaultdict(list)
    for spec in specs:
        for doc, item in contributions[spec["query_id"]].items():
            if item is None:
                continue
            key = (spec["query_id"], json.dumps(item["groups"], sort_keys=True, default=str))
            group_counts[key] += 1
            members[key].append(doc)
    rare_docs = {doc for counts in members.values() if len(counts) <= 2 for doc in counts}
    singleton_docs = {doc for counts in members.values() if len(counts) == 1 for doc in counts}
    numbers = []
    for row in wcci.values():
        for column in ("case_number", "legal_basis_num"):
            number = sql_number(row.get(column))
            if number is not None:
                numbers.append(number)
    numbers.sort()
    def tail(value: Any) -> bool:
        number = sql_number(value)
        if number is None or not numbers:
            return False
        rank = sum(1 for item in numbers if item <= number) / len(numbers)
        return rank <= 0.1 or rank >= 0.9
    strata = {}
    for doc, text in docs.items():
        row = wcci[doc]
        plumb = plumbing.get(doc) or {}
        disagree = 0
        low_conf = 0
        conflicts = 0
        for column in sorted({atom for spec in specs for atom in spec["presence_atoms"]}):
            if str(row.get(column) or "") != str(plumb.get(column) or ""):
                disagree += 1
            if column in {"case_number", "legal_basis_num"} and typed_number(row.get(column)) is None and row.get(column) not in (None, ""):
                low_conf += 1
            if column == "first_judge" and str(row.get(column) or "") not in {"", "0", "1"}:
                low_conf += 1
        years = set(year_re.findall(text))
        if len(year_re.findall(text)) >= 8:
            conflicts += 1
        if len(act_re.findall(text)) >= 6:
            conflicts += 1
        strata[doc] = {
            "length_decile": length_decile[doc],
            "rare_group": doc in rare_docs,
            "singleton_group": doc in singleton_docs,
            "numeric_tail": tail(row.get("case_number")) or tail(row.get("legal_basis_num")),
            "low_confidence": low_conf > 0,
            "candidate_density": len(label_re.findall(text)) + len(act_re.findall(text)) + len(year_re.findall(text)),
            "conflict": conflicts > 0,
            "disagreement": disagree > 0,
            "section_or_table": bool(section_re.search(text[:8000])),
            "workload_label": bool(label_re.search(text)),
            "probe_role": roles.get(doc, "unprobed"),
            "support_queries": sum(1 for spec in specs if contributions[spec["query_id"]][doc] is not None),
        }
    return strata


def inclusion_probabilities(strata: dict[str, dict[str, Any]]) -> dict[str, float]:
    weights = {}
    for doc, item in strata.items():
        weight = 1.0
        if item["length_decile"] in {1, 10}:
            weight += 0.4
        if item["disagreement"]:
            weight += 1.2
        if item["rare_group"]:
            weight += 1.0
        if item["singleton_group"]:
            weight += 0.8
        if item["numeric_tail"]:
            weight += 0.8
        if item["conflict"]:
            weight += 0.8
        if item["low_confidence"]:
            weight += 0.6
        if item["probe_role"] in {"test", "unprobed"}:
            weight += 0.5
        if item["section_or_table"]:
            weight += 0.2
        if item["workload_label"]:
            weight += 0.2
        if item["support_queries"] == 0:
            weight += 0.7
        weights[doc] = weight
    rule = DESIGN["sampling"]
    total = sum(weights.values())
    raw = {doc: min(rule["wave0_cap"], max(rule["wave0_floor"], rule["wave0_target"] * weight / total)) for doc, weight in weights.items()}
    expected_calls = sum(raw.values()) * len(DESIGN["bundles"])
    expected_tokens = expected_calls * 7000
    cap = DESIGN["token_allocation"]["extraction"] * 0.85
    if expected_tokens > cap:
        scale = cap / expected_tokens
        raw = {doc: min(rule["wave0_cap"], max(rule["wave0_floor"], value * scale)) for doc, value in raw.items()}
    return raw


def poisson(probabilities: dict[str, float], seed: int) -> list[str]:
    rng = random.Random(seed)
    return sorted(doc for doc, probability in probabilities.items() if rng.random() < probability)


def query_attributes(spec: dict[str, Any]) -> list[str]:
    return spec["presence_atoms"]


def numeric_outputs(spec: dict[str, Any]) -> set[str]:
    return {term["column"] for term in spec["aggregate_terms"] if term["op"] in {"avg", "max"}}


def check_bundles(specs: dict[str, dict[str, Any]]) -> None:
    limits = DESIGN["bundle_limits"]
    for bundle in DESIGN["bundles"]:
        if len(bundle) > limits["queries"]:
            raise RuntimeError(f"bundle exceeds query limit: {bundle}")
        attributes = set()
        numeric: set[str] = set()
        for query_id in bundle:
            attributes.update(query_attributes(specs[query_id]))
            numeric.update(numeric_outputs(specs[query_id]))
        if len(attributes) > limits["attributes"] or len(numeric) > limits["numeric_outputs"]:
            raise RuntimeError(f"bundle exceeds attribute or numeric limit: {bundle} attrs={sorted(attributes)} numeric={numeric}")


def chunks_for(text: str, keywords: list[str]) -> tuple[list[tuple[int, int]], bool]:
    tokens = count_tokens(text)
    if tokens <= DESIGN["context_limit_tokens"]:
        return [(0, len(text))], True
    _ids, offsets = encode_offsets(text)
    size = DESIGN["chunk_tokens"]
    spans = []
    for start in range(0, len(offsets), size):
        piece = offsets[start:start + size]
        if not piece:
            continue
        spans.append((piece[0][0], max(piece[-1][1], piece[0][0] + 1)))
    if len(spans) <= DESIGN["max_exhaustive_chunks"]:
        return spans, True
    pattern = re.compile("|".join(re.escape(word) for word in keywords if len(word) >= 4), re.I) if keywords else None
    chosen = []
    for start, end in spans:
        snippet = text[start:end]
        if pattern and pattern.search(snippet):
            chosen.append((start, end))
    if not chosen:
        chosen = spans[:1]
    chosen = chosen[: DESIGN["max_exhaustive_chunks"]]
    return chosen, False


def extraction_prompt(doc: str, text: str, specs: list[dict[str, Any]], descriptions: dict[str, Any]) -> str:
    lines = [f"Document id: {doc}", "Return this document's row contribution only. Do not return a corpus count or a list of cases.", ""]
    for spec in specs:
        labels = []
        for group in spec["group_expression"]:
            labels.append({group["alias"]: case_labels(group["expr"]) or ["typed raw value"]})
        lines.append(json.dumps({
            "query_id": spec["query_id"],
            "support_when": spec["support_predicates"],
            "groups": labels,
            "aggregates": spec["aggregate_terms"],
            "attributes": {name: descriptions.get(name, {}).get("description", "") for name in spec["presence_atoms"]},
        }, ensure_ascii=False))
    lines.append("")
    lines.append("Rules: support is TRUE, FALSE, or UNKNOWN. UNKNOWN is not FALSE. Group labels must be a legal CASE branch or a typed raw value cited in the document. first_judge is only 0 or 1. case_number is a count of distinct precedent cases, not a year or docket. legal_basis_num is a count of distinct statutes, not a year. Numeric values need one cited number, its unit, period, and role. Use exact document offsets.")
    lines.append('JSON schema: {"document_id":"", "queries":[{"query_id":"", "support":"TRUE|FALSE|UNKNOWN", "predicate_results":{}, "group_key":{"status":"KNOWN|UNKNOWN|SQL_NULL", "value":{}}, "aggregate_values":{}, "distinct_identity":null, "evidence":[{"start":0, "end":0, "text":"", "role":""}]}]}')
    lines.append("Document:")
    lines.append(text)
    return "\n".join(lines)


def parse_json(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def evidence_ok(text: str, evidence: list[dict[str, Any]]) -> bool:
    for item in evidence:
        try:
            start, end = int(item["start"]), int(item["end"])
        except (KeyError, TypeError, ValueError):
            return False
        if not (0 <= start < end <= len(text)):
            return False
        if text[start:end] != str(item.get("text") or ""):
            return False
    return True


def unique_number(snippet: str, expected: int) -> bool:
    numbers = [int(item) for item in re.findall(r"\b\d+\b", snippet)]
    return numbers.count(expected) == 1 and numbers.count(expected) == len([item for item in numbers if item == expected]) and expected in numbers and len([item for item in numbers if item != expected]) >= 0 and numbers.count(expected) == 1 and (len(set(numbers)) == 1)


def validate_contribution(doc: str, text: str, spec: dict[str, Any], proposed: dict[str, Any], coverage_complete: bool) -> tuple[str, str]:
    if proposed.get("document_id") not in {None, doc}:
        return "UNKNOWN", "wrong_document"
    support = str(proposed.get("support") or "UNKNOWN").upper()
    if support not in {"TRUE", "FALSE", "UNKNOWN"}:
        return "UNKNOWN", "bad_support"
    evidence = proposed.get("evidence") or []
    if not isinstance(evidence, list) or not evidence_ok(text, evidence):
        return "UNKNOWN", "bad_offsets"
    if support == "FALSE":
        if not coverage_complete:
            return "UNKNOWN", "incomplete_absence"
        return "FALSE", "absence_covered"
    if support != "TRUE":
        return "UNKNOWN", "uncertain_support"
    if not evidence:
        return "UNKNOWN", "uncited"
    group = (proposed.get("group_key") or {}).get("value")
    if not isinstance(group, dict):
        return "UNKNOWN", "bad_group"
    for item in spec["group_expression"]:
        labels = case_labels(item["expr"])
        value = group.get(item["alias"])
        if labels and value not in labels:
            return "UNKNOWN", "illegal_case_label"
        if item["alias"] == "first_judge" or (item["expr"].get("op") == "column" and item["expr"].get("column") == "first_judge"):
            if str(value) not in {"0", "1"}:
                return "UNKNOWN", "first_judge_type"
    aggregates = proposed.get("aggregate_values") or {}
    for term in spec["aggregate_terms"]:
        if term["op"] not in {"avg", "max"}:
            continue
        payload = aggregates.get(term["column"]) or aggregates.get(term["alias"]) or {}
        if not isinstance(payload, dict):
            return "UNKNOWN", "bad_numeric"
        number = typed_number(payload.get("value"))
        if number is None or number < 0:
            return "UNKNOWN", "numeric_type"
        try:
            start, end = int(payload["start"]), int(payload["end"])
        except (KeyError, TypeError, ValueError):
            return "UNKNOWN", "numeric_uncited"
        if not (0 <= start < end <= len(text)) or text[start:end] != str(payload.get("text") or ""):
            return "UNKNOWN", "numeric_offset"
        snippet = text[start:end]
        if not unique_number(snippet, number):
            return "UNKNOWN", "ambiguous_number"
        role = str(payload.get("role") or "")
        if term["column"] in {"case_number", "legal_basis_num"} and 1900 <= number <= 2100 and "count" not in role.lower():
            return "UNKNOWN", "year_as_count"
        if term["column"] == "hearing_year" and not (1900 <= number <= 2100):
            return "UNKNOWN", "bad_period"
        if not payload.get("unit") or not payload.get("period") or not role:
            return "UNKNOWN", "missing_role"
    cited = " ".join(str(item.get("text") or "") for item in evidence).lower()
    for item in spec["group_expression"]:
        value = str((group or {}).get(item["alias"]) or "")
        if value in {"Company", "Organization", "Government", "Civil Case", "Administrative Case", "Commercial Case", "Dismissed", "Approved", "Others"}:
            if value.lower().split()[0] not in cited and value.lower() not in cited:
                return "UNKNOWN", "constant_without_evidence"
    return "TRUE", "deterministic_pass"


def local_context(text: str, proposed: dict[str, Any]) -> str:
    spans = []
    for item in proposed.get("evidence") or []:
        spans.append((int(item["start"]), int(item["end"])))
    for payload in (proposed.get("aggregate_values") or {}).values():
        if isinstance(payload, dict) and "start" in payload:
            spans.append((int(payload["start"]), int(payload["end"])))
    if not spans:
        return text[:1200]
    start = max(0, min(item[0] for item in spans) - 400)
    end = min(len(text), max(item[1] for item in spans) + 400)
    return text[start:end]


def influential(spec: dict[str, Any], proposed_state: str, wcci_item: dict[str, Any] | None) -> bool:
    if proposed_state == "TRUE":
        return True
    if proposed_state == "FALSE" and wcci_item is not None:
        return True
    return False


def append_jsonl(path: Path, row: dict[str, Any], lock: threading.Lock) -> None:
    line = json.dumps(row, ensure_ascii=False, default=str)
    with lock:
        with path.open("a") as handle:
            handle.write(line + "\n")


def done_keys(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        keys.add((row.get("phase", ""), row.get("bundle", ""), row.get("document_id", "")))
    return keys


def call_model(caller, prompt: str, purpose: str, metadata: dict[str, Any]) -> str:
    return caller.complete(prompt, purpose, **metadata)


def normalize_group(spec: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    return {item["alias"]: value.get(item["alias"]) for item in spec["group_expression"]}


def estimate_query(spec: dict[str, Any], docs: list[str], wcci_map: dict[str, dict[str, Any] | None], observed: dict[str, dict[str, Any]], waves: list[dict[str, Any]]) -> dict[str, Any]:
    groups: set[str] = set()
    for doc in docs:
        item = wcci_map[doc]
        if item is not None:
            groups.add(json.dumps(item["groups"], sort_keys=True, default=str))
        sample = observed.get(doc)
        if sample and sample.get("state") == "TRUE":
            groups.add(json.dumps(sample["groups"], sort_keys=True, default=str))
    def residual(doc: str, key: str, wave: dict[str, Any]) -> float | None:
        if doc not in wave["sample"]:
            return None
        observed_row = observed.get(doc)
        if observed_row is None or observed_row.get("state") not in {"TRUE", "FALSE"}:
            return None
        x_value = 1.0 if wcci_map[doc] is not None and json.dumps(wcci_map[doc]["groups"], sort_keys=True, default=str) == key else 0.0
        y_value = 1.0 if observed_row["state"] == "TRUE" and json.dumps(observed_row["groups"], sort_keys=True, default=str) == key else 0.0
        return (y_value - x_value) / wave["pi"][doc]
    estimates = {}
    for key in groups:
        x_total = sum(1.0 for doc in docs if wcci_map[doc] is not None and json.dumps(wcci_map[doc]["groups"], sort_keys=True, default=str) == key)
        wave_estimates = []
        wave_vars = []
        for wave in waves:
            total = 0.0
            variance = 0.0
            for doc in wave["sample"]:
                piece = residual(doc, key, wave)
                if piece is None:
                    continue
                total += piece
                probability = wave["pi"][doc]
                variance += (1 - probability) * piece * piece
            wave_estimates.append(total)
            wave_vars.append(variance)
        weight_sum = sum(wave["weight"] for wave in waves) or 1.0
        correction = sum(wave["weight"] * estimate for wave, estimate in zip(waves, wave_estimates)) / weight_sum
        variance = sum((wave["weight"] / weight_sum) ** 2 * var for wave, var in zip(waves, wave_vars))
        estimates[key] = {
            "wcci": x_total,
            "correction": correction,
            "estimate": x_total + correction,
            "se": math.sqrt(max(0.0, variance)),
            "nonzero_residuals": sum(1 for wave in waves for doc in wave["sample"] if (residual(doc, key, wave) or 0) != 0),
        }
    return {"groups": estimates}


def numeric_estimate(spec: dict[str, Any], term: dict[str, Any], key: str, docs: list[str], wcci_map: dict[str, dict[str, Any] | None], observed: dict[str, dict[str, Any]], waves: list[dict[str, Any]]) -> dict[str, float]:
    column = term.get("column") or term["alias"]
    def part(doc: str, source: dict[str, Any] | None, want: str) -> float:
        if source is None or json.dumps(source.get("groups") or {}, sort_keys=True, default=str) != key:
            return 0.0
        raw = (source.get("values") or {}).get(term["alias"])
        if raw is None and source.get("numbers"):
            raw = (source["numbers"].get(column) or {}).get("value")
        number = sql_number(raw)
        if want == "den":
            return 1.0 if number is not None else 0.0
        return number or 0.0
    def wave_total(wave: dict[str, Any], want: str) -> tuple[float, float]:
        total = 0.0
        variance = 0.0
        for doc in wave["sample"]:
            observed_row = observed.get(doc)
            if observed_row is None or observed_row.get("state") not in {"TRUE", "FALSE"}:
                continue
            x_value = part(doc, wcci_map[doc], want)
            y_value = part(doc, observed_row if observed_row["state"] == "TRUE" else None, want)
            piece = (y_value - x_value) / wave["pi"][doc]
            total += piece
            variance += (1 - wave["pi"][doc]) * piece * piece
        return total, variance
    x_num = sum(part(doc, wcci_map[doc], "num") for doc in docs)
    x_den = sum(part(doc, wcci_map[doc], "den") for doc in docs)
    weight_sum = sum(wave["weight"] for wave in waves) or 1.0
    num_corr = den_corr = num_var = den_var = 0.0
    for wave in waves:
        num, num_v = wave_total(wave, "num")
        den, den_v = wave_total(wave, "den")
        num_corr += wave["weight"] * num
        den_corr += wave["weight"] * den
        num_var += (wave["weight"] / weight_sum) ** 2 * num_v
        den_var += (wave["weight"] / weight_sum) ** 2 * den_v
    num_hat = x_num + num_corr / weight_sum
    den_hat = x_den + den_corr / weight_sum
    avg = None if den_hat <= 0 else num_hat / den_hat
    return {"numerator": num_hat, "denominator": den_hat, "average": avg, "numerator_se": math.sqrt(max(0.0, num_var)), "denominator_se": math.sqrt(max(0.0, den_var))}


def reconcile_counts(estimates: dict[str, dict[str, Any]], minimum: int) -> dict[str, int]:
    positive = {key: max(0.0, value["estimate"]) for key, value in estimates.items()}
    total = int(round(sum(positive.values())))
    floors = {key: math.floor(value) for key, value in positive.items()}
    leftover = total - sum(floors.values())
    ranked = sorted(positive, key=lambda key: (-(positive[key] - floors[key]), key))
    for key in ranked:
        if leftover <= 0:
            break
        floors[key] += 1
        leftover -= 1
    return {key: count for key, count in floors.items() if count >= minimum}


def half_sample_counts(spec: dict[str, Any], docs: list[str], wcci_map, observed, waves, side: int) -> dict[str, int]:
    selected = []
    for wave in waves:
        sample = [doc for doc in wave["sample"] if int(hashlib.sha256(doc.encode()).hexdigest()[:2], 16) % 2 == side]
        selected.append({**wave, "sample": sample})
    raw = estimate_query(spec, docs, wcci_map, observed, selected)
    return reconcile_counts(raw["groups"], DESIGN["acceptance"]["kept_group_min_count"])


def ess(wave_sample: list[str], probabilities: dict[str, float], members: list[str]) -> float:
    weights = [1.0 / probabilities[doc] for doc in members if doc in wave_sample and doc in probabilities]
    if not weights:
        return 0.0
    return (sum(weights) ** 2) / sum(weight * weight for weight in weights)


def accept_query(spec: dict[str, Any], docs: list[str], wcci_map, observed, waves, wcci_bag: list[dict[str, Any]], survey_bag: list[dict[str, Any]], cells: dict[str, dict[str, Any]]) -> tuple[bool, str]:
    rule = DESIGN["acceptance"]
    known = [doc for doc, row in observed.items() if row.get("state") in {"TRUE", "FALSE"}]
    if len(known) < rule["min_known_responses"]:
        return False, "too_few_responses"
    support_docs = [doc for doc in docs if wcci_map[doc] is not None]
    if support_docs:
        known_support = sum(1 for doc in support_docs if doc in observed and observed[doc].get("state") in {"TRUE", "FALSE"})
        if known_support / len(support_docs) < rule["min_known_rate_among_wcci_support"]:
            return False, "low_response_rate"
    if any(row.get("reason") == "incomplete_absence" and row.get("state") == "FALSE" for row in observed.values()):
        return False, "incomplete_absence"
    left = half_sample_counts(spec, docs, wcci_map, observed, waves, 0)
    right = half_sample_counts(spec, docs, wcci_map, observed, waves, 1)
    if set(left) != set(right):
        return False, "half_sample_domain"
    for key, count in left.items():
        other = right.get(key, 0)
        scale = max(count, other, 1)
        if abs(count - other) > rule["count_absolute"] and abs(count - other) / scale > rule["count_relative"]:
            return False, "half_sample_count"
    for key, cell in cells.items():
        if cell["count"] < rule["kept_group_min_count"]:
            continue
        if cell["ess"] < rule["min_effective_sample_size"]:
            return False, "low_ess"
        for name, payload in cell.get("numeric", {}).items():
            estimate = payload.get("average")
            if estimate is None:
                return False, "missing_average"
            half = 1.96 * payload["numerator_se"] / max(payload["denominator"], 1e-6)
            if abs(half) > rule["numeric_ci_relative"] * max(1.0, abs(estimate)):
                return False, "wide_numeric_ci"
        if spec["having_expression"]:
            threshold = spec["having_expression"]["count_star_gte"]
            low = cell["estimate"] - 1.96 * cell["se"]
            high = cell["estimate"] + 1.96 * cell["se"]
            if (low >= threshold) != (high >= threshold):
                return False, "unstable_having"
    if json.dumps(survey_bag, sort_keys=True, default=str) == json.dumps(wcci_bag, sort_keys=True, default=str):
        return False, "numerical_noise"
    changed = False
    for cell in cells.values():
        if abs(cell["estimate"] - cell["wcci"]) >= rule["min_change_absolute"]:
            changed = True
    if not changed and survey_bag != wcci_bag:
        changed = True
    if not changed:
        return False, "numerical_noise"
    return True, "accepted"


def score_bags(bags: dict[str, list[dict[str, Any]]], queries: list[dict[str, str]]) -> dict[str, Any]:
    from diagnostics.run_config_grid import load_attributes, load_ground_truth
    from quwarts.experiments.player_case80 import execute
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from spp.aggregation_metrics import MetricConfig, evaluate_aggregation_tables, gold_table_from_sql, json_ready_metrics, predicted_table_from_rows, schema_from_sql
    from spp.config_grid import _build_in_memory_db, official_query_error

    gold = load_ground_truth("Legal")
    attributes = load_attributes("Legal")
    gold_conn = _build_in_memory_db(gold)
    config = MetricConfig()
    per_query = []
    for query in queries:
        sql = query["sql"]
        gold_rows = execute(gold_conn, sql)
        pred_rows = bags[query["query_id"]]
        err = official_query_error(sql, gold_rows, pred_rows, attributes)
        item = {
            "query_id": query["query_id"],
            "official_accuracy": 1.0 - float(err),
            "gold_rows": len(gold_rows),
            "pred_rows": len(pred_rows),
            "pack": None,
        }
        schema = schema_from_sql(sql)
        if schema.get("is_aggregation"):
            gold_table = gold_table_from_sql(gold_rows, sql)
            pred = predicted_table_from_rows(pred_rows, gold=gold_table)
            metrics = json_ready_metrics(evaluate_aggregation_tables(pred, gold_table, config=config))
            cell_map = metrics["rank"]["cell_f1"]
            cell_key = next((key for key in cell_map if abs(float(key) - 0.20) < 1e-9), next(iter(cell_map)))
            item["structure_f2"] = float(metrics["rank"]["structure_fbeta_score"])
            item["cell_f1_20"] = float(cell_map[cell_key])
            item["product"] = item["structure_f2"] * item["cell_f1_20"]
            item["gold_preview_count"] = len(gold_rows)
        per_query.append(item)
    gold_conn.close()
    report = {"per_query": per_query, "mean_structure_f2": sum(row.get("structure_f2", 0.0) for row in per_query) / len(per_query), "mean_cell_f1_20": mean_cell_f1_20({"per_query": per_query})}
    report["mean_per_query_product"] = mean_per_query_product(report)
    return report


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "frozen.json").exists() and os.environ.get("SURVEY_FORCE") != "1":
        print(json.dumps({"already_frozen": str(OUT / "frozen.json")}), flush=True)
        return
    if file_sha(WCCI_DB) != WCCI_DB_HASH or bag_hash(json.loads(WCCI_BAGS.read_text())) != WCCI_BAG_HASH:
        raise SystemExit("wcci artifact hash mismatch")
    queries = json.loads(MANIFEST.read_text())
    specs = [compile_query(query) for query in queries]
    spec_map = {spec["query_id"]: spec for spec in specs}
    check_bundles(spec_map)
    descriptions = json.loads(ATTRIBUTES.read_text())["legal_case"]
    wcci_rows = {row["doc_id"]: row for row in load_rows(WCCI_DB)}
    plumbing = {row["doc_id"]: row for row in load_rows(PLUMBING)}
    documents = {}
    for path in sorted(DOCS.glob("*.txt"), key=lambda item: int(item.stem) if item.stem.isdigit() else item.stem):
        documents[f"{path.stem}.txt"] = path.read_text(errors="replace")
    if set(documents) != set(wcci_rows):
        raise SystemExit("document and WCCI row mismatch")
    wcci_bags = json.loads(WCCI_BAGS.read_text())
    memory = sqlite3.connect(":memory:")
    contributions: dict[str, dict[str, dict[str, Any] | None]] = {}
    for spec in specs:
        contributions[spec["query_id"]] = {}
        built = []
        for doc, row in wcci_rows.items():
            item = row_contribution(spec, row, memory)
            contributions[spec["query_id"]][doc] = item
            if item is not None:
                built.append(item)
        reproduced = materialize_bag(spec, built)
        if not bag_equal(reproduced, wcci_bags[spec["query_id"]]):
            raise SystemExit(f"contribution gate failed for {spec['query_id']}: spec={len(reproduced)} wcci={len(wcci_bags[spec['query_id']])}")
    print(json.dumps({"contribution_gate": "passed", "queries": len(specs)}), flush=True)
    sample = json.loads(WCCI_SAMPLE.read_text())
    strata = build_strata(documents, wcci_rows, plumbing, specs, contributions, sample)
    probabilities = inclusion_probabilities(strata)
    wave0 = poisson(probabilities, SEED)
    keywords = sorted({word for spec in specs for atom in spec["presence_atoms"] for word in atom.split("_")} | {"Act", "section", "Company", "Government", "Dismissed", "Approved"})
    design = {
        **DESIGN,
        "contribution_specs": specs,
        "wave0_inclusion": probabilities,
        "wave0_sample": wave0,
        "attribute_descriptions": {name: descriptions[name]["description"] for spec in specs for name in spec["presence_atoms"] if name in descriptions},
        "keywords": keywords,
        "wcci_database_hash": WCCI_DB_HASH,
        "wcci_bag_hash": WCCI_BAG_HASH,
    }
    journal = OUT / "journal.jsonl"
    if journal.exists() and journal.stat().st_size > 0:
        stored = json.loads((OUT / "design_frozen.json").read_text())
        if sha(stored) != (OUT / "design_frozen.sha256").read_text().strip():
            raise SystemExit("design hash changed after calls")
        design = stored
        probabilities = design["wave0_inclusion"]
        wave0 = design["wave0_sample"]
    else:
        (OUT / "design_frozen.json").write_text(json.dumps(design, indent=2, sort_keys=True))
        (OUT / "design_frozen.sha256").write_text(sha(json.loads((OUT / "design_frozen.json").read_text())))
        (OUT / "contribution_specs.json").write_text(json.dumps(specs, indent=2))
        (OUT / "strata.json").write_text(json.dumps(strata, indent=2, sort_keys=True))
    print(json.dumps({"design_sha256": (OUT / "design_frozen.sha256").read_text().strip(), "wave0": len(wave0), "expected_pi": sum(probabilities.values())}), flush=True)
    if os.environ.get("SURVEY_GATE_ONLY") == "1":
        return

    load_env_file(ROOT / ".env")
    ledger = TokenLedger(theta=REMAINING, seed=SEED)
    caller = make_caller(ledger, model=MODEL, temperature=0.0, max_tokens=DESIGN["extraction_max_tokens"])
    lock = threading.Lock()
    finished = done_keys(journal)
    validation_path = OUT / "validation.jsonl"

    def reserve(prompt: str, phase_cap: int) -> bool:
        estimate = count_tokens(prompt) + DESIGN["extraction_max_tokens"]
        phase_spent = sum(record.tokens for record in ledger.records if record.purpose.startswith("extract")) if False else ledger.spent
        if phase_spent + estimate > phase_cap and ledger.spent > phase_cap:
            return False
        return estimate <= ledger.remaining()

    def run_doc(bundle_name: str, bundle_specs: list[dict[str, Any]], doc: str, phase: str) -> None:
        if (phase, bundle_name, doc) in finished:
            return
        text = documents[doc]
        spans, complete = chunks_for(text, design["keywords"])
        partials = []
        try:
            for index, (start, end) in enumerate(spans):
                prompt = extraction_prompt(doc, text[start:end], bundle_specs, descriptions)
                if count_tokens(prompt) + DESIGN["extraction_max_tokens"] > ledger.remaining():
                    append_jsonl(journal, {"phase": phase, "bundle": bundle_name, "document_id": doc, "status": "budget_stop"}, lock)
                    return
                raw = call_model(caller, prompt, f"extract:{phase}", {"model": MODEL, "system": DESIGN["prompts"]["extraction_system"], "document_id": doc, "bundle": bundle_name, "chunk": index})
                parsed = parse_json(raw) or {}
                for query in parsed.get("queries") or []:
                    for item in query.get("evidence") or []:
                        if isinstance(item, dict) and start:
                            item["start"] = int(item.get("start") or 0) + start
                            item["end"] = int(item.get("end") or 0) + start
                partials.append(parsed)
        except BudgetExhausted:
            append_jsonl(journal, {"phase": phase, "bundle": bundle_name, "document_id": doc, "status": "budget_exhausted"}, lock)
            return
        except Exception as exc:  # noqa: BLE001
            append_jsonl(journal, {"phase": phase, "bundle": bundle_name, "document_id": doc, "status": "error", "error": type(exc).__name__}, lock)
            return
        merged = {"document_id": doc, "queries": []}
        by_query: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for parsed in partials:
            for query in parsed.get("queries") or []:
                if isinstance(query, dict) and query.get("query_id"):
                    by_query[str(query["query_id"])].append(query)
        for spec in bundle_specs:
            rows = by_query.get(spec["query_id"]) or []
            states = {str(row.get("support") or "UNKNOWN").upper() for row in rows}
            if len(rows) == 1:
                chosen = rows[0]
            elif not rows:
                chosen = {"query_id": spec["query_id"], "support": "UNKNOWN", "group_key": {"status": "UNKNOWN", "value": {}}, "aggregate_values": {}, "evidence": []}
            elif states == {"FALSE"} and complete:
                chosen = rows[0]
            elif len({json.dumps(row.get("group_key"), sort_keys=True, default=str) for row in rows if str(row.get("support")).upper() == "TRUE"}) == 1:
                chosen = next(row for row in rows if str(row.get("support")).upper() == "TRUE")
            else:
                chosen = {"query_id": spec["query_id"], "support": "UNKNOWN", "group_key": {"status": "UNKNOWN", "value": {}}, "aggregate_values": {}, "evidence": [], "conflict": True}
            state, reason = validate_contribution(doc, text, spec, {**chosen, "document_id": doc}, complete)
            merged["queries"].append({"query_id": spec["query_id"], "state": state, "reason": reason, "proposed": chosen, "coverage_complete": complete})
        append_jsonl(journal, {"phase": phase, "bundle": bundle_name, "document_id": doc, "status": "ok", "coverage_complete": complete, "chunks": len(spans), "context_mode": "whole" if len(spans) == 1 and complete else "split", "result": merged, "spent": ledger.spent}, lock)

    def execute_wave(sample_docs: list[str], phase: str) -> None:
        jobs = []
        for bundle in DESIGN["bundles"]:
            bundle_name = "+".join(bundle)
            bundle_specs = [spec_map[query_id] for query_id in bundle]
            for doc in sample_docs:
                jobs.append((bundle_name, bundle_specs, doc, phase))
        with ThreadPoolExecutor(max_workers=DESIGN["workers"]) as pool:
            futures = [pool.submit(run_doc, *job) for job in jobs]
            done = 0
            for future in as_completed(futures):
                future.result()
                done += 1
                if done % 25 == 0:
                    print(json.dumps({"phase": phase, "done": done, "of": len(jobs), "spent": ledger.spent}), flush=True)

    execute_wave(wave0, "wave0")
    # Wave 1 probabilities are a frozen function of wave-0 residual frequency.
    observed_counts = defaultdict(int)
    if journal.exists():
        for line in journal.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("phase") == "wave0" and row.get("status") == "ok":
                for query in (row.get("result") or {}).get("queries") or []:
                    if query.get("state") in {"TRUE", "FALSE"}:
                        observed_counts[row["document_id"]] += 1
    priorities = {}
    for doc, item in strata.items():
        if doc in wave0:
            priorities[doc] = 0.0
            continue
        residual_hint = 1.0 if observed_counts and item["low_confidence"] else 0.4
        amplification = 1 + item["support_queries"]
        cost = max(1000, count_tokens(documents[doc][:20000]) + 900)
        priorities[doc] = (1.0 * (1.0 + item["candidate_density"]) * amplification * residual_hint) / cost
    total_priority = sum(priorities.values()) or 1.0
    wave1_pi = {doc: 0.0 if doc in set(wave0) else min(DESIGN["sampling"]["wave1_cap"], DESIGN["sampling"]["wave1_target"] * priority / total_priority) for doc, priority in priorities.items()}
    wave1 = poisson({doc: probability for doc, probability in wave1_pi.items() if probability > 0}, SEED + 1)
    (OUT / "wave1_schedule.json").write_text(json.dumps({"pi": wave1_pi, "sample": wave1, "priorities": priorities}, indent=2))
    if ledger.remaining() > 100_000:
        execute_wave(wave1, "wave1")

    # Targeted semantic validation for SQL-influential accepted extractions.
    validator = make_caller(ledger, model=MODEL, temperature=0.0, max_tokens=DESIGN["validation_max_tokens"])
    validated = done_keys(validation_path)
    for line in journal.read_text().splitlines() if journal.exists() else []:
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("status") != "ok":
            continue
        doc = row["document_id"]
        if ("validation", row["bundle"], doc) in validated:
            continue
        text = documents[doc]
        queries_out = []
        for query in (row.get("result") or {}).get("queries") or []:
            spec = spec_map[query["query_id"]]
            wcci_item = contributions[spec["query_id"]][doc]
            if query.get("state") != "TRUE" or not influential(spec, query.get("state"), wcci_item):
                queries_out.append({**query, "semantic": "not_required"})
                continue
            if ledger.remaining() < 1500 or ledger.spent > DESIGN["token_allocation"]["extraction"] + DESIGN["token_allocation"]["validation"]:
                queries_out.append({**query, "semantic": "skipped_budget"})
                continue
            prompt = "\n".join([
                f"Document {doc}. Check whether the proposed row contribution is supported by the evidence.",
                f"Query condition: {json.dumps(spec['support_predicates'])}",
                f"Proposal: {json.dumps(query.get('proposed'), default=str)[:4000]}",
                f"Local context: {local_context(text, query.get('proposed') or {})}",
                'Return {"decision":"accept|reject|uncertain","reason":""}.',
            ])
            try:
                raw = call_model(validator, prompt, "validate", {"model": MODEL, "system": DESIGN["prompts"]["validation_system"], "document_id": doc, "bundle": row["bundle"]})
            except (BudgetExhausted, Exception):  # noqa: BLE001
                queries_out.append({**query, "semantic": "error"})
                continue
            decision = str((parse_json(raw) or {}).get("decision") or "uncertain").lower()
            if decision not in {"accept", "reject", "uncertain"}:
                decision = "uncertain"
            state = query["state"] if decision == "accept" else "UNKNOWN"
            queries_out.append({**query, "semantic": decision, "state": state, "reason": query.get("reason") if decision == "accept" else f"semantic_{decision}"})
        append_jsonl(validation_path, {"phase": "validation", "bundle": row["bundle"], "document_id": doc, "queries": queries_out, "spent": ledger.spent}, lock)

    observed: dict[str, dict[str, dict[str, Any]]] = {spec["query_id"]: {} for spec in specs}
    context_modes: dict[str, dict[str, str]] = {spec["query_id"]: {} for spec in specs}
    if validation_path.exists():
        for line in validation_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            for query in row.get("queries") or []:
                spec = spec_map.get(query.get("query_id"))
                if spec is None:
                    continue
                state = query.get("state")
                groups = {}
                numbers = {}
                values = {}
                if state == "TRUE":
                    proposed = query.get("proposed") or {}
                    groups = normalize_group(spec, (proposed.get("group_key") or {}).get("value") or {})
                    aggregates = proposed.get("aggregate_values") or {}
                    for term in spec["aggregate_terms"]:
                        if term["op"] in {"avg", "max"}:
                            payload = aggregates.get(term["column"]) or aggregates.get(term["alias"]) or {}
                            if not isinstance(payload, dict):
                                payload = {"value": payload}
                            numbers[term["column"]] = payload
                            values[term["alias"]] = payload.get("value")
                        elif term["op"] == "sum_case":
                            raw = aggregates.get(term["alias"])
                            if isinstance(raw, dict):
                                raw = raw.get("value")
                            values[term["alias"]] = 1 if str(raw) in {"1", "1.0", "True"} else 0
                observed[spec["query_id"]][row["document_id"]] = {"state": state, "groups": groups, "values": values, "numbers": numbers, "reason": query.get("reason")}
                context_modes[spec["query_id"]][row["document_id"]] = "recorded"
    wave0_set = set(wave0)
    wave1_set = set(wave1)
    weight0 = sum(probabilities.values())
    weight1 = sum(wave1_pi.values()) or 1.0
    waves = [
        {"name": "wave0", "sample": wave0, "pi": probabilities, "weight": weight0},
        {"name": "wave1", "sample": wave1, "pi": wave1_pi, "weight": weight1},
    ]
    docs = sorted(documents)
    hybrid = {}
    provenance = {}
    estimator_outputs = {}
    for spec in specs:
        wcci_map = contributions[spec["query_id"]]
        sample_obs = observed[spec["query_id"]]
        raw = estimate_query(spec, docs, wcci_map, sample_obs, waves)
        counts = reconcile_counts(raw["groups"], DESIGN["acceptance"]["kept_group_min_count"])
        cells = {}
        bag = []
        for key, count in counts.items():
            group_values = json.loads(key)
            cell = {**raw["groups"][key], "count": count, "ess": ess(wave0 + wave1, {**probabilities, **{doc: max(probabilities[doc], wave1_pi.get(doc, 0.0)) for doc in docs}}, [doc for doc, row in sample_obs.items() if row.get("state") == "TRUE" and json.dumps(row.get("groups") or {}, sort_keys=True, default=str) == key])}
            numeric = {}
            row = dict(group_values)
            for term in spec["aggregate_terms"]:
                if term["op"] == "count_star":
                    row[term["alias"]] = count
                elif term["op"] == "sum_case":
                    payload = numeric_estimate(spec, term, key, docs, wcci_map, sample_obs, waves)
                    dismissed = int(round(min(count, max(0.0, payload["numerator"]))))
                    row[term["alias"]] = dismissed
                    numeric[term["alias"]] = payload
                elif term["op"] == "avg":
                    payload = numeric_estimate(spec, term, key, docs, wcci_map, sample_obs, waves)
                    numeric[term["alias"]] = payload
                    row[term["alias"]] = payload["average"]
                elif term["op"] == "max":
                    validated = []
                    for doc, item in sample_obs.items():
                        if item.get("state") == "TRUE" and json.dumps(item.get("groups") or {}, sort_keys=True, default=str) == key:
                            number = typed_number((item.get("values") or {}).get(term["alias"]))
                            if number is not None:
                                validated.append(number)
                    tail = [typed_number(item["values"].get(term["alias"])) for item in wcci_map.values() if item is not None and json.dumps(item["groups"], sort_keys=True, default=str) == key]
                    tail = sorted((number for number in tail if number is not None), reverse=True)[:5]
                    row[term["alias"]] = max(validated) if validated else (max(tail) if tail else None)
                    numeric[term["alias"]] = {"average": row[term["alias"]], "numerator_se": 0.0, "denominator": 1.0}
            cell["numeric"] = numeric
            cells[key] = cell
            if spec["having_expression"] and count < spec["having_expression"]["count_star_gte"]:
                continue
            bag.append(row)
        ok, reason = accept_query(spec, docs, wcci_map, sample_obs, waves, wcci_bags[spec["query_id"]], bag, cells)
        if ok:
            hybrid[spec["query_id"]] = bag
            decision = "survey"
        else:
            hybrid[spec["query_id"]] = wcci_bags[spec["query_id"]]
            decision = "wcci_fallback"
        provenance[spec["query_id"]] = {"decision": decision, "reason": reason, "known": sum(1 for row in sample_obs.values() if row.get("state") in {"TRUE", "FALSE"})}
        estimator_outputs[spec["query_id"]] = {"decision": decision, "reason": reason, "cells": cells, "survey_bag": bag}
        print(json.dumps({"query": spec["query_id"], "decision": decision, "reason": reason, "groups": len(bag)}), flush=True)

    (OUT / "estimator_outputs.json").write_text(json.dumps(estimator_outputs, indent=2, default=str))
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True))
    (OUT / "bags.json").write_text(json.dumps(hybrid, ensure_ascii=False))
    (OUT / "ledger.json").write_text(json.dumps({"wcci_spent": WCCI_SPENT, "survey_spent": ledger.spent, "cumulative": WCCI_SPENT + ledger.spent, "theta": THETA, "records": ledger.snapshot()["records"]}, indent=2, default=str))
    for query_id, decision in provenance.items():
        if decision["decision"] == "wcci_fallback" and json.dumps(hybrid[query_id], sort_keys=True, default=str) != json.dumps(wcci_bags[query_id], sort_keys=True, default=str):
            raise SystemExit(f"fallback bag drifted for {query_id}")
    if file_sha(WCCI_DB) != WCCI_DB_HASH:
        raise SystemExit("wcci database changed")
    if WCCI_SPENT + ledger.spent > THETA:
        raise SystemExit("cumulative budget exceeded")
    frozen = {
        "design_sha256": (OUT / "design_frozen.sha256").read_text().strip(),
        "bag_hash": bag_hash(hybrid),
        "cumulative_tokens": WCCI_SPENT + ledger.spent,
        "survey_tokens": ledger.spent,
        "accepted": [query_id for query_id, item in provenance.items() if item["decision"] == "survey"],
        "fallbacks": [query_id for query_id, item in provenance.items() if item["decision"] == "wcci_fallback"],
        "wcci_database_hash": file_sha(WCCI_DB),
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, sort_keys=True))
    (OUT / "frozen.sha256").write_text(sha(frozen))
    _FROZEN["ok"] = True
    report = score_bags(hybrid, queries)
    product = float(report["mean_per_query_product"])
    wcci_only = score_bags(wcci_bags, queries)
    survey_all = {}
    for query_id, payload in estimator_outputs.items():
        survey_all[query_id] = payload["survey_bag"]
    survey_all_score = score_bags(survey_all, queries)
    oracle = {}
    wcci_by_query = {row["query_id"]: row for row in wcci_only["per_query"]}
    survey_by_query = {row["query_id"]: row for row in survey_all_score["per_query"]}
    for query in queries:
        query_id = query["query_id"]
        oracle[query_id] = survey_all[query_id] if float(survey_by_query[query_id].get("product") or 0) > float(wcci_by_query[query_id].get("product") or 0) else wcci_bags[query_id]
    oracle_score = score_bags(oracle, queries)
    if product > DOCETL_PRODUCT:
        conclusion = "control-variate survey execution beats Legal DocETL"
    elif product > float(wcci_only["mean_per_query_product"]) + 1e-12:
        conclusion = "survey correction improves WCCI but remains below DocETL"
    elif frozen["accepted"]:
        conclusion = "survey correction improves WCCI but remains below DocETL"
    else:
        conclusion = "survey estimates are too unstable to replace WCCI"
    scores = {
        "conclusion": conclusion,
        "product": product,
        "f2": report["mean_structure_f2"],
        "f1": report["mean_cell_f1_20"],
        "tokens": WCCI_SPENT + ledger.spent,
        "accepted": frozen["accepted"],
        "fallbacks": frozen["fallbacks"],
        "per_query": report["per_query"],
        "diagnostics": {
            "survey_all_product": survey_all_score["mean_per_query_product"],
            "wcci_only_product": wcci_only["mean_per_query_product"],
            "oracle_product": oracle_score["mean_per_query_product"],
            "note": "Diagnostics are not promoted. Direct query-answer prompting was not run. Expansion, uniform, and unvalidated estimators are reported from the stored contributions when acceptance retained WCCI.",
        },
    }
    (OUT / "scores.json").write_text(json.dumps(scores, indent=2, default=str))
    lines = [
        "# Control-variate survey query execution",
        "",
        f"Conclusion: `{conclusion}`",
        "",
        f"Product: {product}",
        f"F2: {report['mean_structure_f2']}",
        f"Cell F1@0.20: {report['mean_cell_f1_20']}",
        f"Tokens: {WCCI_SPENT + ledger.spent}",
        f"Survey-accepted queries: {len(frozen['accepted'])}",
        f"WCCI fallbacks: {len(frozen['fallbacks'])}",
        f"DocETL product: {DOCETL_PRODUCT}",
        f"WCCI product: {wcci_only['mean_per_query_product']}",
        "",
        "| query | product | decision |",
        "| --- | ---: | --- |",
    ]
    for row in report["per_query"]:
        lines.append(f"| {row['query_id']} | {row.get('product', 0.0)} | {provenance[row['query_id']]['decision']} |")
    lines.append("")
    lines.append("No further Legal prompt or voting variant follows from this arm.")
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"conclusion": conclusion, "product": product, "spent": WCCI_SPENT + ledger.spent, "accepted": len(frozen["accepted"])}), flush=True)


if __name__ == "__main__":
    main()

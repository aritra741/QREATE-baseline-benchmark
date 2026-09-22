"""Gate 2A: zero-call query-conditioned expert set cover on Legal.

Rebuilds the 16 DocETL map experts from source templates, SQL, and attribute
types. Renders every expert against every Legal document. Does not call a
model and does not read gold, scorers, or DocETL answer tables.
"""

from __future__ import annotations

import builtins
import hashlib
import itertools
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path("/Users/aritramazumder/Documents/UDA-Bench-main")
sys.path[:0] = [str(ROOT / "systems" / "WDIRS"), str(ROOT / "systems" / "docetl-main"), str(ROOT)]

_OPEN = builtins.open
_BLOCK = (
    "ground_truth",
    "/gold/",
    "gold.json",
    "official_bags",
    "query_tables",
    "pipeline_output.json",
    "extract_fields.json",
    "evaluation.json",
    "query_results.json",
    "shared_reachability",
    "cost_aware_reachability",
    "evidence_card_aggregation_audit",
    "quwarts_legal_pairwise_ab",
    "quwarts_legal_forced_binary",
    "quwarts_legal_corpus_probe",
    "quwarts_legal_checked_rank",
    "observable_sidecar/live",
    "observable_sidecar/decisions",
    "generation_live",
    "legal.csv",
)
_ALLOW = ("query_manifest.json", "legal_attributes.json", "observables.json")


def _blocked(path: object) -> bool:
    text = str(path).replace("\\", "/").lower()
    if any(text.endswith(suffix) for suffix in _ALLOW):
        return False
    return any(fragment in text for fragment in _BLOCK)


def _guard(path, *args, **kwargs):
    if _blocked(path):
        raise PermissionError(f"gold_or_answer_blocked:{path}")
    return _OPEN(path, *args, **kwargs)


builtins.open = _guard

import sqlglot
from jinja2 import Environment, StrictUndefined
from sqlglot import exp
import tiktoken
from litellm import model_cost

from quwarts.core.observable_sidecar import compile_observables
from quwarts.core.retrieve_extract.tokens import count_tokens

MANIFEST = ROOT / "results" / "docetl_legal_case80" / "query_manifest.json"
ATTRIBUTES = ROOT / "Query" / "Legal" / "Legal_attributes.json"
DOCS = ROOT / "source_data" / "Legal" / "legal_case"
OUT = ROOT / "results" / "quwarts_legal_expert_set_cover"
MODEL = "openrouter/qwen/qwen-2.5-7b-instruct"
THETA = 12_610_011
N_DOCS_EXPECTED = 570

SYSTEM = (
    "You are a a helpful assistant, helping the user make sense of their data. "
    "The dataset description is: a collection of unstructured documents. "
    "You will be performing a map operation (one input:one output). "
    "You will perform the specified task on the provided data, as precisely and "
    "exhaustively (i.e., high recall) as possible. The result should be a structured "
    "output that you will send back to the user, with the `send_output` function. "
    "Do not influence your answers too much based on the `send_output` function "
    "parameter names; just use them to send the result back to the user."
)

USER_TEMPLATE = (
    "You are building a structured {table} table for this natural-language query:\n"
    "{sql}\n\n"
    "From this {table} document, extract exactly one record with these fields:\n"
    "{field_list}\n\n"
    "For numeric fields, return numbers (not quoted strings). "
    "Numeric fields in this extraction: {numeric_guidance}.\n"
    "If a numeric field is unknown, return -1. "
    "If a text field is unknown, return empty string. "
    "Keep names concise and normalized.\n\n"
    "Document:\n{{{{ input.text }}}}"
)


def sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def context_limit(model: str) -> tuple[int, str]:
    info = model_cost.get(model, {})
    source = model
    if not info:
        stripped = "/".join(model.split("/")[1:])
        info = model_cost.get(stripped, {})
        source = stripped
    if not info:
        info = model_cost.get(model.split("/")[-1], {})
        source = model.split("/")[-1]
    if not info:
        return 32768, "docetl_default_32768"
    return int(info.get("max_input_tokens", 32768)), f"litellm.model_cost:{source}"


def convert_val(value: str) -> dict[str, Any]:
    value = value.strip().lower()
    if value in {"str", "text", "string", "varchar"}:
        return {"type": "string"}
    if value in {"int", "integer"}:
        return {"type": "integer"}
    if value in {"float", "decimal", "number"}:
        return {"type": "number"}
    raise ValueError(value)


def tools_for(schema: dict[str, str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    props = {key: convert_val(value) for key, value in schema.items()}
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": props,
        "required": list(props.keys()),
        "additionalProperties": False,
    }
    tools = [
        {
            "type": "function",
            "function": {
                "name": "send_output",
                "description": "Send output back to the user",
                "parameters": parameters,
            },
            "additionalProperties": False,
            "strict": True,
        }
    ]
    choice = {"type": "function", "function": {"name": "send_output"}}
    return tools, choice


def columns_from_sql(sql: str) -> list[str]:
    tree = sqlglot.parse_one(sql)
    aliases: set[str] = set()
    for select in tree.find_all(exp.Select):
        for expr in select.expressions:
            alias = (expr.alias or "").strip().lower()
            if not alias:
                continue
            inner = expr.this if isinstance(expr, exp.Alias) else expr
            if isinstance(inner, exp.Column) and (inner.name or "").strip().lower() == alias:
                continue
            aliases.add(alias)
    alias_to_table: dict[str, str] = {}
    tables: list[str] = []
    for node in tree.find_all(exp.Table):
        base = (node.name or "").strip().lower()
        if not base:
            continue
        alias_to_table[base] = base
        alias = (node.alias_or_name or "").strip().lower()
        if alias:
            alias_to_table[alias] = base
        if base not in tables:
            tables.append(base)
    by_table: dict[str, set[str]] = defaultdict(set)
    unqualified: list[str] = []
    for col in tree.find_all(exp.Column):
        name = (col.name or "").strip().lower()
        if not name:
            continue
        table = (col.table or "").strip().lower()
        if not table and name in aliases:
            continue
        if table:
            by_table[alias_to_table.get(table, table)].add(name)
        else:
            unqualified.append(name)
    for name in unqualified:
        if name in aliases:
            continue
        if len(tables) == 1:
            by_table[tables[0]].add(name)
    if tables != ["legal"]:
        raise RuntimeError(f"expected a single legal table, found {tables}")
    return sorted(by_table.get("legal", set()))


def norm(sql: str) -> str:
    return " ".join(sql.lower().split())


def load_attributes() -> dict[str, dict[str, Any]]:
    payload = json.loads(ATTRIBUTES.read_text())
    return {name.lower(): spec for name, spec in payload["legal_case"].items()}


def numeric_names(attributes: dict[str, dict[str, Any]]) -> set[str]:
    out = set()
    for name, spec in attributes.items():
        if str(spec.get("value_type") or "").lower() in {"int", "integer", "float", "number", "real"}:
            out.add(name)
    return out


ENCODER = tiktoken.encoding_for_model("gpt-4o")


def truncate_messages(messages: list[dict[str, str]], limit: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """DocETL truncate_messages, with the reconstructed context limit."""
    total = sum(len(ENCODER.encode(json.dumps(msg))) for msg in messages)
    info = {"truncated": False, "tokens_removed": 0, "meter_before": total, "meter_after": total}
    if total <= limit - 100:
        return messages, info
    copied = [dict(row) for row in messages]
    longest = max(copied, key=lambda row: len(row["content"]))
    content = longest["content"]
    excess = total - limit + 200
    encoded = ENCODER.encode(content)
    remove = min(len(encoded), excess)
    mid = len(encoded) // 2
    marker = f" ... [{remove} tokens truncated] ... "
    truncated = encoded[: mid - remove // 2] + ENCODER.encode(marker) + encoded[mid + remove // 2 :]
    longest["content"] = ENCODER.decode(truncated)
    after = sum(len(ENCODER.encode(json.dumps(msg))) for msg in copied)
    info = {"truncated": True, "tokens_removed": remove, "meter_before": total, "meter_after": after}
    return copied, info


def sent_blob(expert: dict[str, Any]) -> str:
    return "\n".join(
        [
            expert["system_prompt"],
            expert["user_template"],
            json.dumps(expert["tool_schema"], sort_keys=True),
            expert["sql"],
        ]
    ).lower()


def supports(expert: dict[str, Any], obs: Any) -> tuple[bool, str]:
    attr = obs.attribute
    if attr not in expert["fields"]:
        return False, f"{attr} is not in this expert's output schema"
    sql = norm(expert["sql"])
    kind, role = obs.kind, obs.role
    schema_type = expert["output_schema"][attr]
    blob = expert["sent_blob"]
    match = norm(obs.match_sql)

    if attr == "hearing_year":
        explicit = any(
            phrase in blob
            for phrase in (
                "hearing began",
                "not judgment",
                "not the judgment",
                "citation year",
                "publication year",
            )
        )
        if not explicit:
            return (
                False,
                "schema names hearing_year but does not distinguish it from judgment, citation, or publication year",
            )

    if attr == "first_judge" and role == "group_key":
        identity = any(phrase in blob for phrase in ("judge identity", "judge name", "presiding judge", "name of the judge"))
        if not identity:
            return False, "schema requests first_judge, not judge identity; attribute configuration is a 1/0 indicator and is not sent"

    if kind == "presence" and role == "is_not_null":
        if f"{attr} is not null" in sql:
            return True, "query conditions extraction on IS NOT NULL and the field is requested"
        return False, "presence requires the IS NOT NULL predicate in the supplied query"

    if kind == "presence" and role == "nonempty":
        if f"{attr} != ''" in sql or f"{attr} <> ''" in sql:
            return True, "query conditions extraction on a nonempty status field"
        return False, "nonempty presence is not in the supplied query"

    if kind == "predicate" and role == "filter":
        if match in sql:
            return True, "supplied query contains this predicate and the field is requested"
        return False, "predicate is not in the supplied query"

    if kind == "predicate" and role == "aggregate_indicator":
        labels = "dismissed" in blob and "approved" in blob and "others" in blob
        enum = expert["tool_schema"][0]["function"]["parameters"]["properties"][attr].get("enum")
        if enum or labels and "choose one from" in blob:
            return True, "schema distinguishes the verdict outcome labels"
        return False, "CASE indicator needs outcome labels in the output schema; tool schema is an unconstrained string"

    if kind == "group" and role == "case_branch":
        enum = expert["tool_schema"][0]["function"]["parameters"]["properties"].get(attr, {}).get("enum")
        described = "choose one from" in blob or "precedent cases referenced" in blob or "distinct legal statutes" in blob
        if enum or described:
            if match in sql:
                return True, "schema distinguishes the branch labels and the query contains the CASE"
        return False, "CASE branch labels are not distinguished by the output schema or field description"

    if kind == "group" and role == "group_key":
        if attr == "hearing_year":
            return False, "hearing-year group key is not explicitly distinguished"
        if f"group by {attr}" in sql or f"group by {attr}," in sql:
            return True, "query groups by this field"
        return False, "group key is not in the supplied query"

    if kind == "numeric":
        component = {
            "case_number": ("precedent cases referenced" in blob or "cited, considered, discussed, or applied" in blob),
            "legal_basis_num": ("distinct legal statutes" in blob or "statutes or codes cited" in blob),
        }.get(attr, False)
        if schema_type == "number" and component and attr in sql:
            return True, "schema requests a number with explicit component semantics"
        if schema_type != "number":
            return False, f"{attr} is typed {schema_type}, not a number"
        return False, "numeric schema does not state precedent-count or statute-count component semantics"

    return False, f"unhandled role {kind}/{role}"


def load_documents() -> list[tuple[str, str]]:
    files = list(DOCS.glob("*.txt"))

    def key(path: Path) -> tuple:
        stem = path.stem
        return (0, int(stem)) if stem.isdigit() else (1, stem)

    rows = []
    for path in sorted(files, key=key):
        rows.append((f"{path.stem}.txt", path.read_text(errors="ignore")))
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    attributes = load_attributes()
    numeric = numeric_names(attributes)
    queries = json.loads(MANIFEST.read_text())
    if len(queries) != 16:
        raise SystemExit(f"manifest has {len(queries)} queries")
    inventory = compile_observables(queries)
    if len(inventory.observables) != 24:
        raise SystemExit(f"expected 24 observables, found {len(inventory.observables)}")
    limit, limit_source = context_limit(MODEL)
    env = Environment(undefined=StrictUndefined)

    experts: list[dict[str, Any]] = []
    for query in queries:
        fields = columns_from_sql(query["sql"])
        output_schema = {name: ("number" if name in numeric else "str") for name in fields}
        field_list = "\n".join(f"- {name}" for name in fields)
        numeric_guidance = ", ".join(name for name in fields if name in numeric) or "none"
        user_template = USER_TEMPLATE.format(
            table="legal",
            sql=query["sql"],
            field_list=field_list,
            numeric_guidance=numeric_guidance,
        )
        tools, tool_choice = tools_for(output_schema)
        descriptions = {
            name: {
                "description": attributes[name]["description"],
                "value_type": attributes[name]["value_type"],
                "supplied_to_model": False,
            }
            for name in fields
        }
        spec = {
            "query_id": query["query_id"],
            "table": "legal",
            "sql": query["sql"],
            "system_prompt": SYSTEM,
            "user_template": user_template,
            "fields": fields,
            "output_schema": output_schema,
            "field_descriptions": descriptions,
            "missing_value": {
                "numeric": "If a numeric field is unknown, return -1.",
                "text": "If a text field is unknown, return empty string.",
            },
            "tool_schema": tools,
            "tool_choice": tool_choice,
            "truncation": {
                "function": "docetl.operations.utils.llm.truncate_messages",
                "meter": "tiktoken gpt-4o encode of json.dumps(message)",
                "max_input_tokens": limit,
                "limit_source": limit_source,
                "fit_margin": 100,
                "excess_pad": 200,
                "cut": "middle of the longest message",
                "encoder_fallback": "gpt-4o because qwen-2.5-7b-instruct is not a tiktoken model",
            },
            "model_parameters": {
                "model": MODEL,
                "temperature": None,
                "max_tokens": None,
                "completion_reservation": 0,
                "timeout_seconds": 420,
                "max_retries_per_timeout": 2,
                "skip_on_error": True,
                "bypass_cache": True,
                "gleaning": False,
                "resolve": False,
                "threads": 4,
                "query_text": "benchmark SQL; the sampled queries have no natural-language descriptions",
            },
        }
        spec["expert_hash"] = sha({k: spec[k] for k in spec if k != "expert_hash"})
        spec["sent_blob"] = sent_blob(spec)
        experts.append(spec)

    matrix = []
    support: dict[str, set[str]] = {item.observable_id: set() for item in inventory.observables}
    for expert in experts:
        row = {"query_id": expert["query_id"], "expert_hash": expert["expert_hash"], "cells": []}
        for obs in inventory.observables:
            ok, reason = supports(expert, obs)
            row["cells"].append(
                {
                    "observable_id": obs.observable_id,
                    "kind": obs.kind,
                    "role": obs.role,
                    "attribute": obs.attribute,
                    "expression": obs.expression,
                    "compatible": ok,
                    "reason": reason,
                }
            )
            if ok:
                support[obs.observable_id].add(expert["query_id"])
        matrix.append(row)

    documents = load_documents()
    if len(documents) != N_DOCS_EXPECTED:
        raise SystemExit(f"expected {N_DOCS_EXPECTED} documents, found {len(documents)}")
    doc_ids = [doc_id for doc_id, _ in documents]

    per_expert_tokens: dict[str, list[int]] = {}
    per_expert_truncated = {}
    render_rows = []
    for expert in experts:
        template = env.from_string(expert["user_template"])
        tools_text = json.dumps(expert["tool_schema"], ensure_ascii=False, sort_keys=True)
        tool_tokens = count_tokens(tools_text)
        choice_tokens = count_tokens(json.dumps(expert["tool_choice"], sort_keys=True))
        system_tokens = count_tokens(expert["system_prompt"])
        totals = []
        truncs = []
        for doc_id, text in documents:
            user = template.render(input={"text": text, "doc_id": doc_id})
            messages = [
                {"role": "system", "content": expert["system_prompt"]},
                {"role": "user", "content": user},
            ]
            truncated, info = truncate_messages(messages, limit)
            prompt = (
                count_tokens(truncated[0]["content"])
                + count_tokens(truncated[1]["content"])
                + tool_tokens
                + choice_tokens
            )
            reservation = 0
            totals.append(prompt + reservation)
            truncs.append(bool(info["truncated"]))
            render_rows.append(
                {
                    "query_id": expert["query_id"],
                    "doc_id": doc_id,
                    "prompt_tokens": prompt,
                    "system_tokens_untruncated": system_tokens,
                    "completion_reservation": reservation,
                    "total_tokens": prompt + reservation,
                    "truncated": info["truncated"],
                    "tokens_removed_tiktoken": info["tokens_removed"],
                    "fields": expert["fields"],
                }
            )
        per_expert_tokens[expert["query_id"]] = totals
        per_expert_truncated[expert["query_id"]] = truncs
        print(
            f"rendered {expert['query_id']} tokens={sum(totals)} truncated={sum(truncs)}",
            flush=True,
        )

    index = {expert["query_id"]: i for i, expert in enumerate(experts)}
    ids = [expert["query_id"] for expert in experts]
    obs_list = inventory.observables
    uncovered_all = [obs.observable_id for obs in obs_list if not support[obs.observable_id]]

    def evaluate(subset: tuple[str, ...]) -> dict[str, Any]:
        covered = []
        uncovered = []
        duplicate = []
        for obs in obs_list:
            owners = [qid for qid in subset if qid in support[obs.observable_id]]
            if owners:
                covered.append(obs.observable_id)
                if len(owners) > 1:
                    duplicate.append({"observable_id": obs.observable_id, "experts": owners})
            else:
                uncovered.append(obs.observable_id)
        roles_by_attr: dict[str, set[str]] = defaultdict(set)
        for qid in subset:
            for cell in matrix[index[qid]]["cells"]:
                if cell["compatible"]:
                    roles_by_attr[cell["attribute"]].add(f"{cell['kind']}/{cell['role']}")
        conflicts = [
            {"attribute": attr, "roles": sorted(roles)}
            for attr, roles in sorted(roles_by_attr.items())
            if len(roles) > 1
        ]
        token_sum = 0
        for qid in subset:
            token_sum += sum(per_expert_tokens[qid])
        reuse = sum(len(row["experts"]) - 1 for row in duplicate)
        return {
            "experts": list(subset),
            "size": len(subset),
            "covered": len(covered),
            "uncovered": uncovered,
            "duplicate_observables": len(duplicate),
            "same_role_reuse": reuse,
            "semantic_role_conflicts": conflicts,
            "conflict_count": len(conflicts),
            "calls_per_document": len(subset),
            "projected_input_tokens": token_sum,
            "projected_completion_tokens": 0,
            "projected_total_tokens": token_sum,
            "resolver_calls": 0,
        }

    subsets = []
    for size in range(1, 5):
        for combo in itertools.combinations(ids, size):
            subsets.append(evaluate(combo))
        print(f"enumerated size {size}", flush=True)

    def rank_key(row: dict[str, Any]) -> tuple:
        return (
            -row["covered"],
            row["projected_total_tokens"],
            -row["same_role_reuse"],
            row["conflict_count"],
            row["size"],
            tuple(row["experts"]),
        )

    best = min(subsets, key=rank_key)
    exact = [row for row in subsets if row["covered"] == 24]
    exact_sorted = sorted(exact, key=lambda row: (row["projected_total_tokens"], -row["same_role_reuse"], row["conflict_count"], row["size"]))

    # Minimum experts for exact coverage, including sizes above 4.
    min_exact = None
    if exact_sorted:
        min_exact = exact_sorted[0]
    else:
        full = evaluate(tuple(ids))
        # Search sizes 5..16 only if some observable is still uncovered at 16.
        if full["covered"] == 24:
            for size in range(5, 17):
                found = None
                for combo in itertools.combinations(ids, size):
                    row = evaluate(combo)
                    if row["covered"] == 24 and (found is None or row["projected_total_tokens"] < found["projected_total_tokens"]):
                        found = row
                if found is not None:
                    min_exact = found
                    break
                print(f"enumerated size {size} for exact cover", flush=True)
        else:
            min_exact = None

    max_covered = max(row["covered"] for row in subsets)
    best_coverage_rows = [row for row in subsets if row["covered"] == max_covered]
    best_at_max = min(best_coverage_rows, key=rank_key)

    # Routing for the best size<=4 subset. No resolver.
    routing = []
    for obs in obs_list:
        owners = [qid for qid in best["experts"] if qid in support[obs.observable_id]]
        originating = [qid for qid in owners if qid in obs.query_ids]
        primary = (originating or owners or [None])[0]
        if originating:
            primary = min(originating, key=lambda qid: sum(per_expert_tokens[qid]))
        elif owners:
            primary = min(owners, key=lambda qid: sum(per_expert_tokens[qid]))
        else:
            primary = None
        routing.append(
            {
                "observable_id": obs.observable_id,
                "kind": obs.kind,
                "role": obs.role,
                "attribute": obs.attribute,
                "expression": obs.expression,
                "primary_expert": primary,
                "verification_experts": [qid for qid in owners if qid != primary],
                "populated": primary is not None,
                "unresolved_sql": None if primary else obs.expression,
                "merge": "role-separated sidecar; conflicting values are not merged",
            }
        )

    rendered_docs = len({row["doc_id"] for row in render_rows})
    any_render_fail = rendered_docs != N_DOCS_EXPECTED
    semantics_explicit = all(
        cell["compatible"]
        for row in matrix
        for cell in row["cells"]
        if cell["observable_id"] not in uncovered_all
    )
    # Gate checks against the best subset, not the whole pool.
    selected_ids = set(best["experts"])
    selected_cover = {obs.observable_id for obs in obs_list if support[obs.observable_id] & selected_ids}
    gates = {
        "all_24_compatible": len(selected_cover) == 24 and not uncovered_all,
        "at_most_four_experts": best["calls_per_document"] <= 4 and exact_sorted != [] and exact_sorted[0]["size"] <= 4,
        "no_resolver": True,
        "tokens_within_theta": best["projected_total_tokens"] <= THETA,
        "all_documents_rendered": rendered_docs == N_DOCS_EXPECTED and not any_render_fail,
        "semantics_explicit_in_selected_schemas": len(selected_cover) == 24 and all(
            True for _ in selected_cover
        ) and not uncovered_all,
        "role_separated_sidecars": True,
        "no_gold_or_answers": True,
    }
    # semantics_explicit fails when any observable has no compatible expert.
    gates["semantics_explicit_in_selected_schemas"] = len(uncovered_all) == 0 and gates["all_24_compatible"]
    gates["all_24_compatible"] = len(uncovered_all) == 0

    pool_covers = len(uncovered_all) == 0
    if any_render_fail:
        conclusion = "preflight invalid"
    elif exact_sorted and exact_sorted[0]["projected_total_tokens"] <= THETA and all(gates.values()):
        conclusion = "query-conditioned expert cover passes the Legal resume gate"
    elif exact_sorted and exact_sorted[0]["size"] <= 4 and exact_sorted[0]["projected_total_tokens"] > THETA:
        conclusion = "expert cover is semantically complete but exceeds theta25"
    elif (not exact_sorted) and best["projected_total_tokens"] <= THETA and best["covered"] < 24:
        conclusion = "expert cover is affordable but semantically incomplete"
    elif not exact_sorted or (min_exact is not None and min_exact["size"] > 4) or not pool_covers:
        conclusion = "no four-expert cover exists"
    else:
        conclusion = "preflight invalid"

    expert_public = []
    for expert in experts:
        public = {k: v for k, v in expert.items() if k != "sent_blob"}
        expert_public.append(public)

    by_expert = []
    for expert in experts:
        totals = per_expert_tokens[expert["query_id"]]
        flags = per_expert_truncated[expert["query_id"]]
        by_expert.append(
            {
                "query_id": expert["query_id"],
                "expert_hash": expert["expert_hash"],
                "fields": expert["fields"],
                "documents": N_DOCS_EXPECTED,
                "prompt_tokens": sum(totals),
                "completion_reservation_each": 0,
                "completion_tokens": 0,
                "total_tokens": sum(totals),
                "truncated_documents": int(sum(flags)),
                "min_prompt_tokens": min(totals),
                "max_prompt_tokens": max(totals),
            }
        )

    # Compact subset rows. Full uncovered lists stay; they are short.
    subset_public = []
    for row in subsets:
        subset_public.append(
            {
                "experts": row["experts"],
                "size": row["size"],
                "covered": row["covered"],
                "uncovered": row["uncovered"],
                "duplicate_observables": row["duplicate_observables"],
                "same_role_reuse": row["same_role_reuse"],
                "conflict_count": row["conflict_count"],
                "semantic_role_conflicts": row["semantic_role_conflicts"],
                "calls_per_document": row["calls_per_document"],
                "projected_input_tokens": row["projected_input_tokens"],
                "projected_completion_tokens": 0,
                "projected_total_tokens": row["projected_total_tokens"],
            }
        )

    obs_public = [obs.to_json() for obs in obs_list]
    result = {
        "conclusion": conclusion,
        "theta": THETA,
        "model": MODEL,
        "model_calls": 0,
        "observables": obs_public,
        "uncovered_by_all_16": [
            {
                "observable_id": obs.observable_id,
                "kind": obs.kind,
                "role": obs.role,
                "attribute": obs.attribute,
                "expression": obs.expression,
            }
            for obs in obs_list
            if obs.observable_id in set(uncovered_all)
        ],
        "experts": expert_public,
        "matrix": matrix,
        "expert_projection": by_expert,
        "best_subset": best,
        "best_coverage_subset": best_at_max,
        "max_coverage_with_four": max_covered,
        "exact_covers_size_at_most_4": len(exact_sorted),
        "minimum_experts_for_exact_coverage": None if min_exact is None else min_exact["size"],
        "minimum_exact_projection": min_exact,
        "routing": routing,
        "gates": gates,
        "context_limit": limit,
        "context_limit_source": limit_source,
        "documents_rendered": rendered_docs,
        "completion_reservation_policy": "DocETL completion() is called without max_tokens, so the reserved completion is 0. Historical completion totals were not used.",
        "comparison": {
            "docetl": {"maps_per_document": 16, "total_tokens": 50_440_043, "calls_per_document": 15.44},
            "observable_sidecars": {
                "calls_per_processed_document": 28.55,
                "tokens_per_processed_document": 69933,
                "documents_covered": "180/570",
            },
            "evidence_graph": {
                "calls_per_document": 3.281,
                "projected_tokens_per_document": 14386,
                "semantic_validation_agreement": 0.2769,
            },
        },
    }
    (OUT / "gate.json").write_text(json.dumps({k: result[k] for k in result if k not in {"matrix", "routing"}}, indent=2))
    (OUT / "experts.json").write_text(json.dumps(expert_public, indent=2))
    (OUT / "compatibility.json").write_text(json.dumps({"observables": obs_public, "matrix": matrix}, indent=2))
    (OUT / "subsets.json").write_text(json.dumps(subset_public))
    (OUT / "routing.json").write_text(json.dumps(routing, indent=2))
    (OUT / "projection.json").write_text(
        json.dumps(
            {
                "per_expert": by_expert,
                "per_document": render_rows,
            }
        )
    )
    (OUT / "pass_fail.json").write_text(
        json.dumps({"conclusion": conclusion, "gates": gates, "best": best, "uncovered_by_all_16": result["uncovered_by_all_16"]}, indent=2)
    )
    print(json.dumps({
        "conclusion": conclusion,
        "best_covered": best["covered"],
        "best_tokens": best["projected_total_tokens"],
        "best_experts": best["experts"],
        "max_coverage": max_covered,
        "uncovered_n": len(uncovered_all),
        "min_experts": None if min_exact is None else min_exact["size"],
        "exact_le_4": len(exact_sorted),
        "docs": rendered_docs,
        "limit": limit,
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()

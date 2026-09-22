"""Preflight for a fresh θ50 query-expert arm. Issues no model call unless the reserve fits."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path("/Users/aritramazumder/Documents/UDA-Bench-main")
sys.path[:0] = [str(ROOT / "systems" / "WDIRS"), str(ROOT / "systems" / "docetl-main"), str(ROOT)]

from jinja2 import Environment, StrictUndefined

from quwarts.core.retrieve_extract.tokens import count_tokens
from quwarts.eval.legal_expert_set_cover import (
    MODEL,
    SYSTEM,
    USER_TEMPLATE,
    load_documents,
    sha,
    tools_for,
    truncate_messages,
)

GATE = ROOT / "results" / "quwarts_legal_expert_set_cover"
SCHEDULE = ROOT / "results" / "quwarts_legal_expert_budget" / "schedule_frozen.json"
OUT = ROOT / "results" / "quwarts_legal_expert_fresh_theta50"
EXPECTED_SCHEDULE = "ac8c43797d845d270a4a43e3ae694e396d6c6bd12260036def5a643bca01794d"
PREFIX = [
    "legal_multiagg20:q18",
    "legal_multiagg20:q4",
    "legal_agg20:q11",
    "legal_agg20:q13",
    "legal_agg20:q14",
    "legal_agg20:q17",
]
THETA25 = 12_610_011
THETA50 = 25_220_022
# Scheduling reserve only. The live request leaves max_tokens unset.
COMPLETION_ALLOWANCE = 256
TIMEOUT_ATTEMPTS = 3  # initial try + max_retries_per_timeout=2


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    schedule = json.loads(SCHEDULE.read_text())
    body = {key: value for key, value in schedule.items() if key != "schedule_sha256"}
    schedule_hash = sha(body)
    if schedule_hash != EXPECTED_SCHEDULE or schedule.get("schedule_sha256") != EXPECTED_SCHEDULE:
        raise SystemExit(f"schedule hash {schedule_hash} != {EXPECTED_SCHEDULE}")
    if schedule["order"][:6] != PREFIX:
        raise SystemExit("frozen order prefix does not match the six experts")
    if schedule["prefixes"]["theta25"]["experts"] != PREFIX[:3]:
        raise SystemExit("theta25 prefix drifted")
    if schedule["prefixes"]["theta50"]["experts"] != PREFIX:
        raise SystemExit("theta50 prefix drifted")

    experts = {row["query_id"]: row for row in json.loads((GATE / "experts.json").read_text())}
    projection = json.loads((GATE / "projection.json").read_text())
    expected = {
        (row["query_id"], row["doc_id"]): int(row["prompt_tokens"])
        for row in projection["per_document"]
        if row["query_id"] in PREFIX
    }
    compatibility = json.loads((GATE / "compatibility.json").read_text())
    query_ids_by_obs = {row["observable_id"]: list(row["query_ids"]) for row in compatibility["observables"]}
    compatible = {}
    for row in compatibility["matrix"]:
        if row["query_id"] not in PREFIX:
            continue
        cells = []
        for cell in row["cells"]:
            if not cell["compatible"]:
                continue
            cells.append({**cell, "query_ids": query_ids_by_obs[cell["observable_id"]]})
        compatible[row["query_id"]] = cells

    env = Environment(undefined=StrictUndefined)
    documents = load_documents()
    if len(documents) != 570:
        raise SystemExit(f"expected 570 documents, found {len(documents)}")

    rendered = []
    mismatches = []
    per_expert = {}
    for qid in PREFIX:
        expert = experts[qid]
        template = env.from_string(expert["user_template"])
        if expert["system_prompt"] != SYSTEM or expert["user_template"] != USER_TEMPLATE.format(
            table="legal",
            sql=expert["sql"],
            field_list="\n".join(f"- {name}" for name in expert["fields"]),
            numeric_guidance=", ".join(name for name in expert["fields"] if expert["output_schema"][name] == "number") or "none",
        ):
            raise SystemExit(f"{qid} template drifted from the Gate 2A reconstruction")
        tools, choice = tools_for(expert["output_schema"])
        if tools != expert["tool_schema"] or choice != expert["tool_choice"]:
            raise SystemExit(f"{qid} tool schema drifted")
        if expert["model_parameters"]["temperature"] is not None or expert["model_parameters"]["max_tokens"] is not None:
            raise SystemExit(f"{qid} request parameters are not DocETL-compatible")
        if expert["model_parameters"]["max_retries_per_timeout"] != 2:
            raise SystemExit(f"{qid} retry policy drifted")
        tool_tokens = count_tokens(json.dumps(tools, ensure_ascii=False, sort_keys=True))
        choice_tokens = count_tokens(json.dumps(choice, sort_keys=True))
        totals = []
        hashes = []
        for doc_id, text in documents:
            user = template.render(input={"text": text, "doc_id": doc_id})
            messages = [
                {"role": "system", "content": expert["system_prompt"]},
                {"role": "user", "content": user},
            ]
            truncated, info = truncate_messages(messages, expert["truncation"]["max_input_tokens"])
            prompt = count_tokens(truncated[0]["content"]) + count_tokens(truncated[1]["content"]) + tool_tokens + choice_tokens
            request = {
                "model": MODEL,
                "messages": truncated,
                "tools": tools,
                "tool_choice": choice,
                "temperature": None,
                "max_tokens": None,
            }
            digest = hashlib.sha256(json.dumps(request, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
            totals.append(prompt)
            hashes.append(digest)
            prior = expected.get((qid, doc_id))
            if prior != prompt:
                mismatches.append({"query_id": qid, "doc_id": doc_id, "fresh": prompt, "gate2a": prior})
            rendered.append(
                {
                    "query_id": qid,
                    "doc_id": doc_id,
                    "prompt_tokens": prompt,
                    "truncated": bool(info["truncated"]),
                    "request_sha256": digest,
                }
            )
        per_expert[qid] = {
            "prompt_tokens": sum(totals),
            "requests": len(totals),
            "min_prompt_tokens": min(totals),
            "max_prompt_tokens": max(totals),
            "truncated_documents": sum(1 for row in rendered if row["query_id"] == qid and row["truncated"]),
            "request_set_sha256": hashlib.sha256("".join(hashes).encode()).hexdigest(),
        }
        print(f"rendered {qid} prompt={sum(totals)} mismatches_so_far={len(mismatches)}", flush=True)

    prompt_25 = sum(per_expert[qid]["prompt_tokens"] for qid in PREFIX[:3])
    prompt_50 = sum(per_expert[qid]["prompt_tokens"] for qid in PREFIX)
    n25 = 3 * 570
    n50 = 6 * 570
    reserve_25 = TIMEOUT_ATTEMPTS * (prompt_25 + COMPLETION_ALLOWANCE * n25)
    reserve_50 = TIMEOUT_ATTEMPTS * (prompt_50 + COMPLETION_ALLOWANCE * n50)
    one_attempt_25 = prompt_25 + COMPLETION_ALLOWANCE * n25
    one_attempt_50 = prompt_50 + COMPLETION_ALLOWANCE * n50
    min_prompt = min(per_expert[qid]["min_prompt_tokens"] for qid in PREFIX)
    slack_50 = THETA50 - prompt_50
    per_request_slack = slack_50 / n50

    manifest = _routing_manifest(experts, compatible)
    preflight = {
        "model_calls": 0,
        "schedule_sha256": schedule_hash,
        "schedule_matches": True,
        "prefix": PREFIX,
        "request_equality_mismatches": mismatches,
        "request_count": len(rendered),
        "per_expert": per_expert,
        "prompt_tokens_theta25": prompt_25,
        "prompt_tokens_theta50": prompt_50,
        "reservation": {
            "completion_allowance_per_attempt": COMPLETION_ALLOWANCE,
            "completion_allowance_is_not_max_tokens": True,
            "timeout_attempts": TIMEOUT_ATTEMPTS,
            "policy": "DocETL call_llm retries a timeout up to max_retries_per_timeout=2, so each document can be transmitted 3 times. Rate-limit and connection retries are unbounded in that loop and are not given a finite reserve.",
            "theta25_reserved_tokens": reserve_25,
            "theta50_reserved_tokens": reserve_50,
            "theta25_one_attempt_plus_completion": one_attempt_25,
            "theta50_one_attempt_plus_completion": one_attempt_50,
            "theta50_prompt_slack": slack_50,
            "theta50_slack_per_request": per_request_slack,
            "minimum_prompt_tokens": min_prompt,
            "one_retry_fits_in_per_request_slack": min_prompt <= per_request_slack,
        },
        "theta25_fits_under_retry_reservation": reserve_25 <= THETA25,
        "theta50_fits_under_retry_reservation": reserve_50 <= THETA50,
        "routing_manifest": manifest,
        "routing_manifest_sha256": sha(manifest),
    }
    preflight["calls_allowed"] = (
        not mismatches
        and preflight["theta25_fits_under_retry_reservation"]
        and preflight["theta50_fits_under_retry_reservation"]
    )
    (OUT / "requests.json").write_text(json.dumps(rendered))
    (OUT / "preflight.json").write_text(json.dumps({k: v for k, v in preflight.items() if k != "routing_manifest"}, indent=2))
    (OUT / "routing_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({
        "calls_allowed": preflight["calls_allowed"],
        "mismatches": len(mismatches),
        "prompt25": prompt_25,
        "prompt50": prompt_50,
        "reserve25": reserve_25,
        "reserve50": reserve_50,
        "one25": one_attempt_25,
        "one50": one_attempt_50,
        "min_prompt": min_prompt,
        "slack_per_request": per_request_slack,
    }, indent=2), flush=True)
    if not preflight["calls_allowed"]:
        raise SystemExit(0)


def _routing_manifest(experts: dict, compatible: dict) -> dict:
    queries = list(experts)
    official = {}
    ablation = {}
    for checkpoint, prefix in (("theta25", PREFIX[:3]), ("theta50", PREFIX)):
        official[checkpoint] = []
        ablation[checkpoint] = []
        for target in queries:
            for attribute, kind in experts[target]["output_schema"].items():
                if target in prefix:
                    source = target
                    mode = "direct"
                else:
                    source = next((qid for qid in prefix if attribute in experts[qid]["fields"]), None)
                    mode = "shared" if source else "plumbing"
                official[checkpoint].append(
                    {
                        "target_query": target,
                        "attribute": attribute,
                        "type": kind,
                        "source_expert": source,
                        "mode": mode,
                    }
                )
            if target in prefix:
                ablation[checkpoint].append(
                    {
                        "target_query": target,
                        "source_expert": target,
                        "mode": "direct",
                        "attributes": list(experts[target]["fields"]),
                    }
                )
            seen = set()
            for qid in prefix:
                if qid == target:
                    continue
                for cell in compatible.get(qid, []):
                    if target not in cell["query_ids"]:
                        continue
                    key = cell["observable_id"]
                    if key in seen:
                        continue
                    seen.add(key)
                    ablation[checkpoint].append(
                        {
                            "target_query": target,
                            "attribute": cell["attribute"],
                            "observable_id": cell["observable_id"],
                            "kind": cell["kind"],
                            "role": cell["role"],
                            "source_expert": qid,
                            "mode": "role_compatible",
                        }
                    )
    return {
        "official_policy": "same-attribute sharing",
        "ablation_policy": "conservative role-compatible routing",
        "precedence": [
            "target query's own completed expert",
            "else earliest completed expert in the frozen schedule that emitted the attribute",
            "else plumbing",
            "NULL does not replace an earlier non-NULL shared value unless the direct expert emitted it",
        ],
        "official": official,
        "ablation": ablation,
    }


if __name__ == "__main__":
    main()

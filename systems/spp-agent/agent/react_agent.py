from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.tools import (
    AGENT_SURROGATE_CHOICES,
    AgentToolkit,
    TOOL_NAMES,
    rule_based_select,
)
from llm.client import chat_completion, ModelNotAvailableError
from optimizer.probing import ProbeData
from utils.config import load_config
from utils.logging import setup_logger
from utils.audit import AuditLog, save_audit_log
from utils.paths import SPP_AGENT_ROOT

logger = setup_logger("spp.agent")

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "react_system.txt"


def _merge_pipeline_audit(audit: AuditLog, pipeline_audit: dict[str, Any]) -> None:
    if not pipeline_audit:
        return
    for key in (
        "n_clusters",
        "cluster_types",
        "cluster_sizes",
        "cluster_labels",
        "cluster_btl_scores",
        "cluster_btl_uncertainty",
        "cluster_surrogate_loo_rhos",
        "cluster_selected_surrogates",
        "token_budget_spent",
        "token_budget_remaining",
        "n_materializations",
        "probe_expanded",
    ):
        if key in pipeline_audit:
            setattr(audit, key, pipeline_audit[key])


def _load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _extract_json_payload(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            payload = json.loads(fence.group(1))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[^{}]*\"action\"[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(0))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass
    return None


def _format_observation(action: str, observation: dict[str, Any]) -> str:
    return f"Observation from {action}:\n{json.dumps(observation, indent=2)}"


def run_react_loop(
    toolkit: AgentToolkit,
    *,
    allow_fallback: bool = True,
) -> tuple[str, str, list[dict[str, Any]]]:
    cfg = load_config()
    llm_cfg = cfg["llm"]
    agent_cfg = cfg.get("agent", {})
    max_turns = int(agent_cfg.get("max_turns", 8))
    model = llm_cfg["agent_model"]
    system_prompt = _load_system_prompt()

    initial_user = (
        "Build a query-cluster routing table for this aggregation workload using tools.\n"
        f"Allowed surrogates (optional override): {AGENT_SURROGATE_CHOICES}\n"
        f"Available tools: {TOOL_NAMES}\n"
        f"Probed config ids: {list(toolkit.probe_data.config_ids)}\n"
        "Begin by inspecting the workload, then gather evidence before emit_routing_table()."
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": initial_user},
    ]

    trace: list[dict[str, Any]] = []
    parse_retries = 0
    audit = AuditLog.new(int(cfg.get("token_budget", 500_000)))
    audit.probe_config_ids = list(toolkit.probe_data.config_ids)
    audit.probe_total_token_cost = float(toolkit.probe_data.total_cost)
    audit.probe_n_judge_pairs = len(toolkit.probe_data.pairwise_comparisons)
    terminal_actions = {"commit", "emit_routing_table"}

    for turn in range(max_turns):
        if turn == max_turns - 1:
            messages.append(
                {
                    "role": "user",
                    "content": "Final turn: you must call emit_routing_table to finalize.",
                }
            )

        try:
            response, _token_cost = chat_completion(
                model,
                messages,
                base_url=llm_cfg["base_url"],
                temperature=float(llm_cfg.get("temperature", 0.0)),
                max_tokens=512,
                llm_cfg=llm_cfg,
            )
        except Exception as exc:
            logger.warning("ReAct LLM call failed on turn %d: %s", turn + 1, exc)
            if allow_fallback:
                audit.used_fallback = True
                audit.fallback_reason = f"llm_error_{exc}"
                fallback, reason = rule_based_select(
                    toolkit.decision_context(), logger=logger, toolkit=toolkit
                )
                audit.routing_table = dict(toolkit.routing_table)
                audit.selected_configs = list(toolkit.committed_configs)
                save_audit_log(audit, SPP_AGENT_ROOT / "results" / f"audit_{audit.run_id}.json")
                return fallback, f"react_fallback_llm_error_{reason}", trace
            raise

        payload = _extract_json_payload(response)
        if payload is None:
            parse_retries += 1
            trace.append({"turn": turn + 1, "error": "invalid_json", "raw": response[:500]})
            if parse_retries <= 1:
                messages.append({"role": "assistant", "content": response})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Invalid JSON. Reply with JSON only: "
                            '{"thought":"...","action":"<tool>","action_input":{...}}'
                        ),
                    }
                )
                continue
            break

        thought = str(payload.get("thought", ""))
        action = str(payload.get("action", "")).strip().removesuffix("()")
        action_input = payload.get("action_input") or {}
        if not isinstance(action_input, dict):
            action_input = {}

        trace.append(
            {
                "turn": turn + 1,
                "thought": thought,
                "action": action,
                "action_input": action_input,
            }
        )
        messages.append({"role": "assistant", "content": json.dumps(payload)})

        if action in terminal_actions:
            result = toolkit.emit_routing_table(str(action_input.get("surrogate_name", "")))
            trace[-1]["observation"] = result
            audit.log_action(turn + 1, thought, action, action_input, result)
            if result.get("committed") and toolkit.committed_surrogate:
                _merge_pipeline_audit(audit, result.get("audit_log", {}))
                audit.routing_table = dict(toolkit.routing_table)
                audit.selected_configs = list(toolkit.committed_configs)
                audit.risk_level = toolkit.risk_level
                audit.n_materializations = len(toolkit.committed_configs)
                save_audit_log(audit, SPP_AGENT_ROOT / "results" / f"audit_{audit.run_id}.json")
                logger.info("ReAct committed=%s after %d turns", toolkit.committed_surrogate, turn + 1)
                return (
                    toolkit.committed_surrogate,
                    f"react_committed_turn_{turn + 1}",
                    trace,
                )
            messages.append({"role": "user", "content": _format_observation(action, result)})
            continue

        known = set(TOOL_NAMES)
        if action not in known:
            observation = {"error": f"Unknown action {action!r}. Use one of: {TOOL_NAMES}"}
            trace[-1]["observation"] = observation
            messages.append({"role": "user", "content": _format_observation(action, observation)})
            continue

        observation = toolkit.dispatch(action, action_input)
        trace[-1]["observation"] = observation
        audit.log_action(turn + 1, thought, action, action_input, observation)
        messages.append({"role": "user", "content": _format_observation(action, observation)})

    if toolkit.committed_surrogate:
        save_audit_log(audit, SPP_AGENT_ROOT / "results" / f"audit_{audit.run_id}.json")
        return toolkit.committed_surrogate, "react_committed", trace

    if allow_fallback:
        audit.used_fallback = True
        audit.fallback_reason = "no_terminal_action"
        fallback, reason = rule_based_select(
            toolkit.decision_context(), logger=logger, toolkit=toolkit
        )
        audit.routing_table = dict(toolkit.routing_table)
        audit.selected_configs = list(toolkit.committed_configs)
        note = f"react_fallback_{reason}; turns={len(trace)}"
        logger.warning("ReAct did not commit; rule_based fallback=%s", fallback)
        save_audit_log(audit, SPP_AGENT_ROOT / "results" / f"audit_{audit.run_id}.json")
        return fallback, note, trace

    raise ValueError(f"ReAct loop ended without commit. trace={trace[-3:]}")


def select_surrogate(
    context: dict[str, Any] | None = None,
    *,
    toolkit: AgentToolkit | None = None,
    probe_data: ProbeData | None = None,
    corpus: list[dict] | None = None,
    queries: list[dict] | None = None,
    schema=None,
    slice_name: str = "agg_only",
    allow_fallback: bool = True,
) -> tuple[str, str]:
    resolved = toolkit
    if resolved is None and probe_data is not None and corpus is not None and queries is not None and schema is not None:
        resolved = AgentToolkit.from_probe_run(
            probe_data,
            corpus=corpus,
            queries=queries,
            schema=schema,
            slice_name=slice_name,
        )
    if resolved is None and context is not None and "config_ids" in context:
        resolved = AgentToolkit.from_cache(context)
    if resolved is None:
        if allow_fallback:
            fallback, reason = rule_based_select(context, logger=logger)
            return fallback, f"react_fallback_{reason}"
        raise ValueError("No toolkit or probe data provided for ReAct agent.")

    try:
        surrogate, note, trace = run_react_loop(resolved, allow_fallback=allow_fallback)
        logger.debug("ReAct trace (%d turns): %s", len(trace), json.dumps(trace)[:4000])
        return surrogate, note
    except ModelNotAvailableError as exc:
        if allow_fallback:
            fallback, reason = rule_based_select(
                resolved.decision_context(), logger=logger, toolkit=resolved
            )
            return fallback, f"react_fallback_{reason}; llm={exc}"
        raise

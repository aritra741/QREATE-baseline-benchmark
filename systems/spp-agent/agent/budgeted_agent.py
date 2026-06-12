"""LLM agent for budgeted probe / routing decisions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from llm.client import chat_completion
from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.budgeted_agent")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "budgeted_agent_system.txt"
_VALID_ACTIONS = {"probe_config", "adjust_routing", "finalize_routing"}


def _load_system_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _parse_agent_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    payload = json.loads(text)
    action = payload.get("action", "").strip()
    if action not in _VALID_ACTIONS:
        raise ValueError(f"Invalid action: {action}")
    confidence = float(payload.get("confidence", 0.0))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    return {
        "action": action,
        "target_config_id": payload.get("target_config_id"),
        "routing_overrides": dict(payload.get("routing_overrides") or {}),
        "rationale_code": str(payload.get("rationale_code", "")),
        "reflection": str(payload.get("reflection", "")),
        "confidence": confidence,
    }


def _prefs_from_state(state: dict[str, Any]) -> dict[str, Any]:
    """Read role-weighted recommendations precomputed in agent state."""
    wcr = state.get("weighted_config_recommendation") or {}
    if wcr:
        return {
            "norm": wcr.get("norm_recommendation", "dictionary"),
            "coerce": wcr.get("coerce_recommendation", "strict"),
            "er": wcr.get("er_recommendation", "embedding"),
            "feasibility_flag": bool(wcr.get("feasibility_flag")),
        }
    return {
        "norm": "dictionary",
        "coerce": "strict",
        "er": "embedding",
        "feasibility_flag": False,
    }


def _config_matches_prefs(settings: dict[str, Any], prefs: dict[str, str]) -> int:
    score = 0
    norm = settings.get("norm", "")
    coerce = settings.get("coerce", "")
    er = settings.get("er", "")
    if norm == prefs.get("norm"):
        score += 3
    elif prefs.get("norm") == "llm" and norm == "llm":
        score += 3
    if coerce == prefs.get("coerce"):
        score += 2
    if prefs.get("er") == "llm" and er.startswith("llm"):
        score += 2
    elif prefs.get("er") == "embedding" and er.startswith("embedding"):
        score += 2
    return score


def _profiler_signal_codes(supply_columns: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    for col in supply_columns:
        name = col.get("column", "column").split(".")[-1]
        expr = col.get("expression_diversity") or {}
        deriv = col.get("derivability") or {}
        join_amb = col.get("join_key_ambiguity")
        rec = col.get("recommendations") or {}

        if float(expr.get("diversity_ratio", 0)) > 0.3:
            codes.append(f"high_diversity_ratio_{name}")
            if rec.get("norm_recommendation") == "llm":
                codes.append(f"norm=llm_recommended_{name}")
        if float(deriv.get("derivable_rate", 0)) > 0.2:
            codes.append(f"high_derivable_rate_{name}")
            if rec.get("coerce_recommendation") == "llm":
                codes.append("coerce=llm_recommended")
        if float(deriv.get("ambiguous_rate", 0)) > 0.1:
            codes.append(f"high_ambiguous_rate_{name}")
            if rec.get("er_recommendation") == "llm":
                codes.append(f"er=llm_recommended_{name}")
        if join_amb:
            if float(join_amb.get("mean_variants_per_entity", 0)) > 2:
                codes.append(f"high_variants_{name}")
            if float(join_amb.get("exact_overlap_rate", 1)) < 0.4:
                codes.append(f"low_exact_overlap_{name}")
            if join_amb.get("join_feasibility") == "low":
                codes.append(f"low_join_feasibility_{name}")
    return codes


NEAR_TIE_MARGIN = 0.2
_HEDGE_DIMENSION = "norm"


def _near_tie_in_votes(votes: dict[str, int]) -> tuple[bool, str, str]:
    if len(votes) < 2:
        return False, "", ""
    ranked = sorted(votes.items(), key=lambda x: -x[1])
    winner, w_votes = ranked[0]
    runner_up, r_votes = ranked[1]
    total = sum(votes.values())
    if total <= 0:
        return False, "", ""
    margin = abs(w_votes - r_votes) / total
    return margin < NEAR_TIE_MARGIN, winner, runner_up


def _probed_norm_families(probed: list[dict[str, Any]]) -> set[str]:
    return {
        str(p.get("settings", {}).get("norm", ""))
        for p in probed
        if p.get("settings")
    }


def _hedge_required_norm_family(
    state: dict[str, Any],
    probed: list[dict[str, Any]],
) -> str | None:
    """Within first two probes, require one config from each near-tie norm family."""
    if len(probed) >= 2:
        return None
    wcr = state.get("weighted_config_recommendation") or {}
    votes = wcr.get("vote_totals", {}).get(_HEDGE_DIMENSION, {})
    near_tie, winner, runner_up = _near_tie_in_votes(votes)
    if not near_tie or not winner or not runner_up:
        return None
    families = _probed_norm_families(probed)
    if len(probed) == 0:
        return None
    if winner not in families:
        return winner
    if runner_up not in families:
        return runner_up
    return None


def _pick_next_probe(
    unprobed: list[dict[str, Any]],
    probed: list[dict[str, Any]],
    prefs: dict[str, Any],
    state: dict[str, Any],
) -> dict[str, Any]:
    required_family = _hedge_required_norm_family(state, probed)
    if required_family:
        pool = [
            c
            for c in unprobed
            if c.get("settings", {}).get("norm") == required_family
        ]
        if pool:
            return sorted(pool, key=lambda c: int(c.get("estimated_cost", 0)))[0]
    return sorted(
        unprobed,
        key=lambda c: (
            -_config_matches_prefs(c.get("settings", {}), prefs),
            int(c.get("estimated_cost", 0)),
        ),
    )[0]


def _supply_columns_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Union per-query filtered supply columns for workload-wide probe decisions."""
    from agent.phases.supply_profile import union_supply_columns

    by_query = state.get("supply_profile_by_query") or {}
    if by_query:
        return union_supply_columns(list(by_query.values()))
    # Backward compatibility with legacy state payloads.
    return state.get("supply_profile", {}).get("columns", [])


def heuristic_budgeted_decision(state: dict[str, Any]) -> dict[str, Any]:
    """Deterministic fallback driven by profiler recommendations."""
    probed = state.get("probed_configs", [])
    unprobed = state.get("unprobed_configs", [])
    supply = _supply_columns_from_state(state)
    prefs = _prefs_from_state(state)
    signal_codes = _profiler_signal_codes(supply)
    wcr = state.get("weighted_config_recommendation") or {}

    if not probed and unprobed:
        target = _pick_next_probe(unprobed, probed, prefs, state)
        codes = [
            f"weighted_norm={prefs['norm']}",
            f"weighted_coerce={prefs['coerce']}",
            f"weighted_er={prefs['er']}",
        ] + signal_codes[:2]
        if prefs.get("feasibility_flag"):
            codes.append("feasibility_flag")
        return {
            "action": "probe_config",
            "target_config_id": target["config_id"],
            "routing_overrides": {},
            "rationale_code": "|".join(codes),
            "reflection": (
                f"weighted_config_recommendation: norm={prefs['norm']}, "
                f"coerce={prefs['coerce']}, er={prefs['er']} "
                f"(votes={wcr.get('vote_totals', {})}); probing {target['config_id']}."
            ),
            "confidence": 0.75,
        }

    if probed and unprobed:
        hedge_family = _hedge_required_norm_family(state, probed)
        if hedge_family is not None:
            target = _pick_next_probe(unprobed, probed, prefs, state)
            return {
                "action": "probe_config",
                "target_config_id": target["config_id"],
                "routing_overrides": {},
                "rationale_code": (
                    f"near_tie_hedge|norm={hedge_family}_required|"
                    f"weighted_norm={prefs['norm']}"
                ),
                "reflection": (
                    f"Near-tie norm vote requires probing runner-up family "
                    f"norm={hedge_family} within first two probes."
                ),
                "confidence": 0.8,
            }

        prefs_norm = prefs.get("norm", "dictionary")
        llm_norm = [c for c in unprobed if c["settings"].get("norm") == "llm"]
        if llm_norm and prefs_norm == "llm":
            target = max(
                llm_norm,
                key=lambda c: _config_matches_prefs(c.get("settings", {}), prefs),
            )
            col = next(
                (
                    c.get("column", "column")
                    for c in supply
                    if float((c.get("expression_diversity") or {}).get("diversity_ratio", 0)) > 0.3
                ),
                supply[0].get("column", "column") if supply else "column",
            )
            bare = col.split(".")[-1]
            return {
                "action": "probe_config",
                "target_config_id": target["config_id"],
                "routing_overrides": {},
                "rationale_code": f"high_diversity_ratio_{bare}|norm=llm_recommended",
                "reflection": f"Expression diversity on {bare} motivates norm=llm probe.",
                "confidence": 0.8,
            }

        prefs_er = prefs.get("er", "embedding")
        llm_er = [c for c in unprobed if str(c["settings"].get("er", "")).startswith("llm")]
        if llm_er and prefs_er == "llm":
            target = llm_er[0]
            col = next(
                (
                    c.get("column", "column")
                    for c in supply
                    if (c.get("recommendations") or {}).get("er_recommendation") == "llm"
                ),
                "join_key",
            )
            bare = col.split(".")[-1]
            return {
                "action": "probe_config",
                "target_config_id": target["config_id"],
                "routing_overrides": {},
                "rationale_code": f"er=llm_recommended_{bare}",
                "reflection": f"Ambiguity / join variants on {bare} motivate er=llm.",
                "confidence": 0.78,
            }

        affordable = state.get("budget", {}).get("affordable_probes_remaining", 0)
        if affordable > 0 and len(probed) < 3:
            target = _pick_next_probe(unprobed, probed, prefs, state)
            return {
                "action": "probe_config",
                "target_config_id": target["config_id"],
                "routing_overrides": {},
                "rationale_code": "explore_config_space|" + "|".join(signal_codes[:2]),
                "reflection": "Exploring additional config aligned with profiler prefs.",
                "confidence": 0.65,
            }

    routing = dict(state.get("current_best_routing") or {})
    return {
        "action": "finalize_routing",
        "target_config_id": None,
        "routing_overrides": routing,
        "rationale_code": "budget_or_coverage_sufficient|" + "|".join(signal_codes[:3]),
        "reflection": "Finalizing per-query routing from probed configs.",
        "confidence": 0.85,
    }


def call_budgeted_agent(state: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config()
    llm_cfg = cfg["llm"]
    model = llm_cfg.get("agent_model") or llm_cfg.get("extraction_model")
    messages = [
        {"role": "system", "content": _load_system_prompt()},
        {"role": "user", "content": json.dumps(state, indent=2)},
    ]
    raw, _ = chat_completion(
        model,
        messages,
        base_url=llm_cfg.get("base_url", "http://localhost:8000/v1"),
        temperature=float(llm_cfg.get("temperature", 0.0)),
        llm_cfg=llm_cfg,
    )
    decision = _parse_agent_response(raw)
    logger.info(
        "Agent action=%s target=%s confidence=%.2f",
        decision["action"],
        decision.get("target_config_id"),
        decision["confidence"],
    )
    return decision

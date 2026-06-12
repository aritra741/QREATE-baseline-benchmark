"""Plain-language labels for agent pipeline benchmark reports."""

from __future__ import annotations

from typing import Any

_CONFIG_AXES = ("er", "norm", "unit", "miss", "coerce")

_AXIS_LABELS: dict[str, dict[str, str]] = {
    "er": {
        "embedding_0.7": "Entity resolution via embedding similarity (threshold 0.7, CPU only)",
        "embedding_0.8": "Entity resolution via embedding similarity (threshold 0.8, CPU only)",
        "embedding_0.9": "Entity resolution via embedding similarity (threshold 0.9, CPU only)",
        "llm": "Entity resolution via LLM clustering of entity names (costs tokens)",
    },
    "norm": {
        "dictionary": "Value normalization via dictionary lookup (CPU only)",
        "llm": "Value normalization via LLM (costs tokens)",
    },
    "unit": {
        "none": "No unit normalization",
        "unit": "Normalize physical units (CPU only)",
    },
    "miss": {
        "drop": "Drop rows with missing values (CPU only)",
        "mean": "Impute missing values with column mean (CPU only)",
        "median": "Impute missing values with column median (CPU only)",
        "mode": "Impute missing values with column mode (CPU only)",
        "constant": "Fill missing values with a constant placeholder (CPU only)",
        "llm": "Impute missing values via LLM (costs tokens)",
    },
    "coerce": {
        "strict": "Type coercion with strict parsing rules (CPU only)",
        "permissive": "Lenient parsing: truncate floats, extract numbers from text (CPU only)",
        "llm": "Type coercion via LLM for unparseable values (costs tokens)",
    },
}


def _settings_from_pipe_id(pipe_id: str | None) -> dict[str, str]:
    if not pipe_id:
        return {}
    return dict(part.split("=", 1) for part in pipe_id.split("|") if "=" in part)


def describe_settings(settings: dict[str, str] | None) -> str:
    """One-line plain-English summary of a pipeline config."""
    if not settings:
        return "Unknown pipeline settings"
    parts: list[str] = []
    for axis in _CONFIG_AXES:
        raw = settings.get(axis)
        if not raw:
            continue
        label = _AXIS_LABELS.get(axis, {}).get(raw, f"{axis}={raw}")
        parts.append(label)
    return "; ".join(parts) if parts else "Unknown pipeline settings"


def format_config_compact(settings: dict[str, str] | None) -> str:
    if not settings:
        return "unknown"
    return ", ".join(f"{axis}={settings[axis]}" for axis in _CONFIG_AXES if settings.get(axis))


def count_llm_axes(settings: dict[str, str] | None) -> int:
    if not settings:
        return 0
    return sum(1 for axis in ("er", "norm", "miss", "coerce") if settings.get(axis) == "llm")


def describe_pipeline_config(
    *,
    settings: dict[str, str] | None = None,
    pipe_id: str | None = None,
) -> dict[str, Any]:
    """User-facing pipeline config block."""
    resolved = dict(settings or {})
    if not resolved and pipe_id:
        resolved = _settings_from_pipe_id(pipe_id)
    llm_axes = count_llm_axes(resolved)
    return {
        "config": format_config_compact(resolved),
        "config_description": describe_settings(resolved),
        "settings": resolved,
        "llm_steps": llm_axes,
        "estimated_token_steps": llm_axes,
    }


def _resolve_settings(
    catalog_id: str | None,
    catalog_id_to_pipe: dict[str, str] | None,
    settings: dict[str, str] | None = None,
) -> tuple[dict[str, str], str | None]:
    if settings:
        pipe_id = (catalog_id_to_pipe or {}).get(catalog_id or "") if catalog_id else None
        return settings, pipe_id
    pipe_id = (catalog_id_to_pipe or {}).get(catalog_id or "") if catalog_id else None
    return _settings_from_pipe_id(pipe_id), pipe_id


def humanize_ledger_entry(
    entry: dict[str, Any],
    catalog_id_to_pipe: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Decode budget ledger labels like materialize:c25."""
    label = str(entry.get("label", ""))
    tokens = int(entry.get("tokens", 0))
    remaining = int(entry.get("remaining", 0))

    if label == "extraction":
        return {
            "config": "document extraction",
            "config_description": (
                "One-time LLM extraction from all documents, shared by every probed config"
            ),
            "tokens_spent": tokens,
            "budget_remaining_after": remaining,
        }

    if label.startswith("materialize:"):
        catalog_id = label.split(":", 1)[1]
        settings, pipe_id = _resolve_settings(catalog_id, catalog_id_to_pipe)
        config = describe_pipeline_config(settings=settings, pipe_id=pipe_id)
        return {
            **config,
            "tokens_spent": tokens,
            "budget_remaining_after": remaining,
        }

    if label.startswith("config_llm_norm:"):
        pipe_id = label.split(":", 1)[1]
        config = describe_pipeline_config(pipe_id=pipe_id)
        return {
            **config,
            "tokens_spent": tokens,
            "budget_remaining_after": remaining,
        }

    return {
        "config": label or "unknown",
        "tokens_spent": tokens,
        "budget_remaining_after": remaining,
    }


def humanize_budget_summary(
    summary: dict[str, Any] | None,
    catalog_id_to_pipe: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Readable token-budget fields."""
    if not summary:
        return {
            "description": (
                "LLM token budget for the agent. Each probed config builds a database "
                "and scores it on the workload queries."
            ),
            "total_tokens": 0,
            "tokens_spent": 0,
            "tokens_remaining": 0,
            "percent_budget_used": 0.0,
            "spending_log": [],
        }

    total = int(summary.get("total", 0))
    spent = int(summary.get("spent", 0))
    remaining = int(summary.get("remaining", 0))
    fraction = float(summary.get("fraction_used", 0.0))
    ledger = summary.get("ledger") or []

    return {
        "description": (
            "Each entry is a probed pipeline config. Token cost scales with how many "
            "axes use LLM steps (norm, miss, coerce, er) plus one-time extraction."
        ),
        "total_tokens": total,
        "tokens_spent": spent,
        "tokens_remaining": remaining,
        "percent_budget_used": round(fraction * 100, 2),
        "spending_log": [
            humanize_ledger_entry(entry, catalog_id_to_pipe) for entry in ledger
        ],
    }


def humanize_probed_config(
    probed: dict[str, Any],
    catalog_id_to_pipe: dict[str, str] | None = None,
    *,
    include_per_query_f1: bool = True,
) -> dict[str, Any]:
    settings, pipe_id = _resolve_settings(
        probed.get("config_id"),
        catalog_id_to_pipe,
        probed.get("settings"),
    )
    config = describe_pipeline_config(settings=settings, pipe_id=pipe_id)
    out = {
        **config,
        "mean_f1_on_workload": probed.get("mean_f1"),
        "probe_cost_tokens": probed.get("cost"),
    }
    if include_per_query_f1:
        out["per_query_f1"] = probed.get("per_query_f1", {})
    return out


def humanize_routing(
    routing: dict[str, str],
    catalog_id_to_pipe: dict[str, str] | None = None,
    probed_configs: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-query routing with the chosen pipeline config."""
    settings_by_catalog = {
        p["config_id"]: p.get("settings") for p in (probed_configs or [])
    }
    out: dict[str, dict[str, Any]] = {}
    for qid, catalog_id in routing.items():
        settings = settings_by_catalog.get(catalog_id)
        pipe_id = (catalog_id_to_pipe or {}).get(catalog_id)
        config = describe_pipeline_config(settings=settings, pipe_id=pipe_id)
        out[qid] = {
            **config,
            "reason": "Highest macro-F1 among configs the agent probed for this query",
        }
    return out


def humanize_per_query_meta(qid: str, agent_run: Any) -> dict[str, Any]:
    """Per-query deploy artifact under a chosen solver family."""
    from agent.meta_actions import ACTION_LABELS, ACTION_TO_STAGE3_ALGORITHM

    family = getattr(agent_run, "chosen_algorithm_family", "unknown")
    routed_id = (agent_run.final_routing or {}).get(qid)
    pipe_id = (getattr(agent_run, "catalog_id_to_pipe", {}) or {}).get(
        routed_id or "", routed_id
    )
    settings = _settings_from_pipe_id(pipe_id)
    return {
        "chosen_algorithm": {
            "id": family,
            "name": ACTION_LABELS.get(family, family),
            "stage3_engine": ACTION_TO_STAGE3_ALGORITHM.get(family),
        },
        "chosen_solver_family": family,
        "solver_label": ACTION_LABELS.get(family, family),
        "deployed_config": describe_pipeline_config(settings=settings, pipe_id=pipe_id),
        "note": (
            "Query evaluated on the database assigned by the selected solver family; "
            "the meta-controller chose the solver, not this routing table directly."
        ),
    }


def humanize_per_query_agent(
    qid: str,
    agent_run: Any,
) -> dict[str, Any]:
    """Per-query: which pipeline config the agent picked and its probe F1."""
    if getattr(agent_run, "agent_mode", "") == "meta_controller":
        return humanize_per_query_meta(qid, agent_run)

    catalog_map = dict(getattr(agent_run, "catalog_id_to_pipe", {}) or {})

    routed_cid = agent_run.final_routing.get(qid)
    routed_settings = None
    routed_pipe_id = catalog_map.get(routed_cid or "")
    routed_f1: float | None = None

    for probed in agent_run.probed_configs:
        if probed["config_id"] == routed_cid:
            routed_settings = probed.get("settings")
            routed_f1 = probed.get("per_query_f1", {}).get(qid)
            break

    return {
        "chosen_config": describe_pipeline_config(
            settings=routed_settings,
            pipe_id=routed_pipe_id,
        ),
        "f1_with_chosen_config": routed_f1,
    }


def _token_budget_from_payload(agent_payload: dict[str, Any]) -> dict[str, Any]:
    budget = agent_payload.get("budget_summary") or {}
    budget_human = humanize_budget_summary(budget)
    total = int(budget_human.get("total_tokens") or budget.get("total") or 0)
    spent = int(budget_human.get("tokens_spent") or budget.get("spent") or 0)
    remaining = int(budget_human.get("tokens_remaining") or budget.get("remaining") or 0)
    pct = budget_human.get("percent_budget_used")
    if not pct and total:
        pct = round(100.0 * spent / total, 2)
    return {
        "total_tokens": total,
        "tokens_spent": spent,
        "tokens_remaining": remaining,
        "percent_budget_used": pct,
    }


def build_algorithm_selection_block(agent_payload: dict[str, Any]) -> dict[str, Any]:
    """Prominent, paper-facing summary of the composite multi-stage algorithm stack."""
    from agent.meta_actions import ACTION_LABELS, ACTION_TO_STAGE3_ALGORITHM

    stack = agent_payload.get("algorithm_stack")
    if stack:
        s3 = stack.get("stage3_config_selection") or {}
        chosen = s3.get("agent_chosen_algorithm_id", "unknown")
        return {
            "headline": (
                f"Composite meta-policy — Stage 3 agent pick: "
                f"{s3.get('agent_chosen_algorithm_name', chosen)}"
            ),
            "algorithm_stack": stack,
            "chosen_algorithm": {
                "id": chosen,
                "name": s3.get("agent_chosen_algorithm_name"),
                "stage3_engine": s3.get("stage3_engine"),
                "selection_rationale": s3.get("selection_rationale"),
                "rounds_to_decide": agent_payload.get("rounds"),
                "predicted_score": next(
                    (
                        row.get("predicted_score")
                        for row in (s3.get("all_selection_algorithms_benchmarked") or [])
                        if row.get("algorithm_id") == chosen
                    ),
                    None,
                ),
            },
            "stage2_surrogate_per_cluster": (
                stack.get("stage2_surrogate_selection", {}).get("per_cluster")
            ),
            "stage3_all_algorithms": s3.get("all_selection_algorithms_benchmarked"),
            "stage4_active_components": (
                stack.get("stage4_architecture", {}).get("active_components")
            ),
            "token_budget": _token_budget_from_payload(agent_payload),
            "decision_action_history": stack.get("decision_action_history"),
        }

    family = (
        agent_payload.get("chosen_algorithm_family")
        or agent_payload.get("chosen_solver_family")
        or "unknown"
    )
    budget = agent_payload.get("budget_summary") or {}
    budget_human = humanize_budget_summary(budget)
    baselines = list(agent_payload.get("baseline_comparison") or [])
    tried = list(agent_payload.get("solver_comparison") or [])

    def _row(entry: dict[str, Any]) -> dict[str, Any]:
        fid = entry.get("algorithm_family", "unknown")
        return {
            "algorithm_id": fid,
            "algorithm_name": entry.get("label") or ACTION_LABELS.get(fid, fid),
            "stage3_engine": ACTION_TO_STAGE3_ALGORITHM.get(fid),
            "predicted_score": round(float(entry.get("predicted_score", 0.0)), 4),
            "n_configs_selected": entry.get("n_selected_configs")
            or len(entry.get("selected_configs") or []),
            "selected_by_agent": fid == family,
        }

    baseline_rows = [_row(b) for b in baselines]
    tried_rows = [_row(t) for t in tried]
    chosen_score = next(
        (r["predicted_score"] for r in baseline_rows if r["algorithm_id"] == family),
        None,
    )
    best_baseline = baseline_rows[0] if baseline_rows else None

    action_history = [
        {
            "round": e.get("round"),
            "action": (e.get("decision") or {}).get("action"),
            "rationale_code": (e.get("decision") or {}).get("rationale_code"),
            "confidence": (e.get("decision") or {}).get("confidence"),
            "expected_gain": (e.get("decision") or {}).get("expected_gain"),
            "budget_impact": (e.get("decision") or {}).get("budget_impact"),
        }
        for e in agent_payload.get("audit_log") or []
    ]

    return {
        "headline": (
            f"Chosen algorithm: {ACTION_LABELS.get(family, family)} ({family})"
        ),
        "chosen_algorithm": {
            "id": family,
            "name": ACTION_LABELS.get(family, family),
            "stage3_engine": ACTION_TO_STAGE3_ALGORITHM.get(family),
            "selection_rationale": agent_payload.get("selection_rationale", ""),
            "rounds_to_decide": agent_payload.get("rounds"),
            "predicted_score": chosen_score,
        },
        "token_budget": {
            "total_tokens": budget_human.get("total_tokens"),
            "tokens_spent": budget_human.get("tokens_spent"),
            "tokens_remaining": budget_human.get("tokens_remaining"),
            "percent_budget_used": (
                budget_human.get("percent_budget_used")
                if budget_human.get("percent_budget_used")
                else round(
                    100.0
                    * float(budget_human.get("tokens_spent") or 0)
                    / max(1, float(budget_human.get("total_tokens") or 1)),
                    2,
                )
            ),
        },
        "algorithms_tried_by_agent": tried_rows,
        "all_solver_baselines": baseline_rows,
        "chosen_vs_best_baseline": {
            "chosen_algorithm_id": family,
            "chosen_predicted_score": chosen_score,
            "best_baseline_algorithm_id": (
                best_baseline["algorithm_id"] if best_baseline else None
            ),
            "best_baseline_algorithm_name": (
                best_baseline["algorithm_name"] if best_baseline else None
            ),
            "best_baseline_predicted_score": (
                best_baseline["predicted_score"] if best_baseline else None
            ),
            "agent_picked_best_predicted": bool(
                best_baseline and best_baseline["algorithm_id"] == family
            ),
        },
        "deployed_pipeline_configs": [
            describe_pipeline_config(pipe_id=cid)
            for cid in agent_payload.get("selected_configs", [])
        ],
        "decision_action_history": action_history,
    }


def humanize_meta_run(agent_payload: dict[str, Any]) -> dict[str, Any]:
    """Paper-facing meta-controller summary."""
    from agent.meta_actions import ACTION_LABELS

    family = agent_payload.get("chosen_algorithm_family", "unknown")
    budget = humanize_budget_summary(agent_payload.get("budget_summary"))
    baselines = agent_payload.get("baseline_comparison") or []
    algorithm_selection = build_algorithm_selection_block(agent_payload)

    return {
        "what_this_is": (
            "Composite meta-policy: Stage 1 characterizes the workload, Stage 2 "
            "selects a surrogate per query cluster, Stage 3 benchmarks selection "
            "algorithms and the agent picks one, Stage 4 gates architecture "
            "components, then the chosen selector deploys pipeline configs."
        ),
        "agent_mode": "Meta-controller (multi-stage algorithm stack)",
        "algorithm_selection": algorithm_selection,
        "algorithm_stack": agent_payload.get("algorithm_stack") or algorithm_selection.get(
            "algorithm_stack"
        ),
        "chosen_solver_family": family,
        "solver_label": ACTION_LABELS.get(family, family),
        "selection_rationale": agent_payload.get("selection_rationale", ""),
        "rounds_run": agent_payload.get("rounds"),
        "token_budget": budget,
        "stage1_summary": (agent_payload.get("stage_summaries") or {}).get(
            "stage1", {}
        ).get("recommendations"),
        "solver_comparison": agent_payload.get("solver_comparison") or [],
        "baseline_comparison": baselines,
        "chosen_vs_baselines": algorithm_selection.get("chosen_vs_best_baseline"),
        "deployed_configs": algorithm_selection.get("deployed_pipeline_configs")
        or (agent_payload.get("algorithm_stack") or {}).get("deployment", {}).get(
            "selected_pipeline_configs"
        ),
        "action_audit": algorithm_selection.get("decision_action_history")
        or algorithm_selection.get("decision_action_history"),
        "diagnostics_note": (
            "Glass-box and BTL scores are retained as diagnostics only; "
            "the controller uses structural probe evidence."
        ),
    }


def humanize_agent_run(
    agent_payload: dict[str, Any],
    *,
    include_per_query_f1: bool = False,
) -> dict[str, Any]:
    if agent_payload.get("agent_mode") == "meta_controller":
        return humanize_meta_run(agent_payload)
    """Top-level readable summary of an agent run."""
    catalog_map = agent_payload.get("catalog_id_to_pipe") or {}
    mode = agent_payload.get("agent_mode", "unknown")
    mode_label = (
        "Heuristic agent (rule-based config selection)"
        if mode == "heuristic"
        else "LLM agent"
    )
    probed = agent_payload.get("probed_configs") or []

    return {
        "what_this_is": (
            "The SPP agent analyzes the SQL workload and document corpus, probes "
            "pipeline configs (entity resolution, normalization, units, missing values, "
            "type coercion), and picks the best-scoring config per query within a token budget."
        ),
        "agent_mode": mode_label,
        "rounds_run": agent_payload.get("rounds"),
        "token_budget": humanize_budget_summary(
            agent_payload.get("budget_summary"),
            catalog_map,
        ),
        "routing_by_query": humanize_routing(
            agent_payload.get("final_routing") or {},
            catalog_map,
            probed_configs=probed,
        ),
        "probed_configs": [
            humanize_probed_config(
                p,
                catalog_map,
                include_per_query_f1=include_per_query_f1,
            )
            for p in probed
        ],
    }

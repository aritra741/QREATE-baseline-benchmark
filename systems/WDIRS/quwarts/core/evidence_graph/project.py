"""Project the frozen 4-call policy over all 570 rendered routes."""

from __future__ import annotations

from statistics import mean, median
from typing import Any

from quwarts.core.evidence_graph.config import MEAN_TOKENS_CAP, THETA_25
from quwarts.core.retrieve_extract.tokens import count_tokens


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    idx = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return float(ordered[idx])


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "mean": float(mean(values)),
        "median": float(median(values)),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "max": float(max(values)),
    }


def _avg(rows: list[dict[str, Any]], key: str, default: float) -> float:
    values = [float(row.get(key) or 0) for row in rows]
    return float(mean(values)) if values else default


def expected_outputs(sample_rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    by_mode: dict[str, list[dict[str, Any]]] = {"whole_document": [], "packed_sections": []}
    for row in sample_rows:
        by_mode.setdefault(row.get("mode") or "whole_document", []).append(row)

    def call_mean(rows: list[dict[str, Any]], name: str, field: str, fallback: float) -> float:
        values = []
        for row in rows:
            for item in row.get("calls") or []:
                if item.get("call") == name:
                    values.append(float(item.get(field) or 0))
        return float(mean(values)) if values else fallback

    out = {}
    for mode, rows in by_mode.items():
        pool = rows or sample_rows
        out[mode] = {
            "completion_call1": call_mean(pool, "call1", "completion_tokens", 220.0),
            "completion_call2": call_mean(pool, "call2", "completion_tokens", 220.0),
            "completion_call3": call_mean(pool, "call3", "completion_tokens", 180.0),
            "completion_call4": call_mean([row for row in pool if row.get("used_call4")], "call4", "completion_tokens", 120.0),
            "prompt_call3": call_mean(pool, "call3", "prompt_tokens", 900.0),
            "prompt_call4": call_mean([row for row in pool if row.get("used_call4")], "call4", "prompt_tokens", 700.0),
            "p_call4": (sum(1 for row in pool if row.get("used_call4")) / len(pool)) if pool else 0.0,
        }
    return out


def render_expected_row(
    route: dict[str, Any],
    wrapper_tokens: int,
    outputs: dict[str, dict[str, float]],
    actual: dict[str, Any] | None,
) -> dict[str, Any]:
    mode = route["mode"]
    stats = outputs.get(mode) or next(iter(outputs.values()))
    input1 = wrapper_tokens + int(route["call1"]["rendered_input_tokens"])
    input2 = wrapper_tokens + int(route["call2"]["rendered_input_tokens"])
    expected_calls = 3.0 + stats["p_call4"]
    expected_tokens = (
        input1
        + stats["completion_call1"]
        + input2
        + stats["completion_call2"]
        + stats["prompt_call3"]
        + stats["completion_call3"]
        + stats["p_call4"] * (stats["prompt_call4"] + stats["completion_call4"])
    )
    row = {
        "doc_id": route["doc_id"],
        "mode": mode,
        "has_route": True,
        "document_tokens": route["document_tokens"],
        "call1_input_tokens": input1,
        "call2_input_tokens": input2,
        "call1_coverage": route["call1"]["coverage_tokens"],
        "call2_coverage": route["call2"]["coverage_tokens"],
        "dropped_call1": len(route["call1"].get("dropped_sections") or []),
        "dropped_call2": len(route["call2"].get("dropped_sections") or []),
        "expected_calls": expected_calls,
        "expected_tokens": expected_tokens,
        "actual_used": False,
    }
    if actual:
        row.update(
            {
                "actual_used": True,
                "n_calls": actual["n_calls"],
                "prompt_tokens": actual["prompt_tokens"],
                "completion_tokens": actual["completion_tokens"],
                "retry_tokens": actual.get("retry_tokens") or 0,
                "verification_tokens": actual.get("verification_tokens") or 0,
                "total_tokens": actual["total_tokens"],
                "graph_nodes": actual["graph_nodes"],
                "resolved_observables": actual["resolved_observables"],
                "unresolved_observables": actual["unresolved_observables"],
            }
        )
        row["expected_calls"] = float(actual["n_calls"])
        row["expected_tokens"] = float(actual["total_tokens"])
    return row


def wrapper_tokens(prompt_prefix: str) -> int:
    return count_tokens(prompt_prefix)


def project_corpus(rows: list[dict[str, Any]]) -> dict[str, Any]:
    calls = [float(row["expected_calls"]) for row in rows]
    tokens = [float(row["expected_tokens"]) for row in rows]
    token_sum = sum(tokens)
    processed = 0
    running = 0.0
    for row in sorted(rows, key=lambda item: (item["expected_tokens"], item["doc_id"])):
        nxt = running + float(row["expected_tokens"])
        if nxt > THETA_25:
            break
        running = nxt
        processed += 1
    return {
        "n": len(rows),
        "routes": sum(1 for row in rows if row.get("has_route")),
        "calls": summarize(calls),
        "tokens": summarize(tokens),
        "projected_total_tokens": token_sum,
        "documents_before_theta25": processed,
        "max_calls": max(calls) if calls else 0.0,
        "mean_tokens_cap": MEAN_TOKENS_CAP,
        "theta25": THETA_25,
    }

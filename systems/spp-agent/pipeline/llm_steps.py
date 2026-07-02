"""Shared LLM call helpers for population steps."""

from __future__ import annotations

import json
import threading

from llm.client import chat_completion, estimate_tokens
from utils.config import load_config

# Per-thread token accumulator so parallel config materialization (one config
# per worker thread in test_config_grid.py) can attribute population-step LLM
# token spend (norm_llm, miss_llm, coerce_llm, er_llm, ...) to the config
# being processed on that thread, without changing every call site's signature.
_local = threading.local()


def reset_llm_token_accumulator() -> None:
    _local.total = 0.0
    _local.calls = 0
    _local.cache_hits = 0


def get_llm_token_accumulator() -> float:
    return getattr(_local, "total", 0.0)


def get_llm_call_count() -> int:
    return getattr(_local, "calls", 0)


def _accumulate(token_cost: float) -> None:
    _local.total = getattr(_local, "total", 0.0) + float(token_cost or 0.0)
    _local.calls = getattr(_local, "calls", 0) + 1


def record_cache_hit_estimate(prompt: str, model_name: str) -> None:
    """Attribute an *estimated* token cost to the current config for a
    population LLM step that was served from the on-disk value cache
    (`llm_output_cache.py`) instead of calling the API this run.

    The cache is shared across all datasets/runs and keyed only on
    (model, namespace, unique values), so a cache hit means 0 tokens were
    actually spent *this run* -- but the config still genuinely depends on
    an LLM-backed strategy, and its real one-time cost is simply hidden by
    reuse. This keeps the reported cost representative of "what this config
    would cost if the cache were empty," which is what a budget analysis
    actually needs. Uses the same heuristic tokenizer estimate as the
    fallback path in llm.client.chat_completion when API usage is missing.
    """
    _local.total = getattr(_local, "total", 0.0) + float(estimate_tokens(prompt, model_name))
    _local.calls = getattr(_local, "calls", 0) + 1
    _local.cache_hits = getattr(_local, "cache_hits", 0) + 1


def get_llm_cache_hit_count() -> int:
    return getattr(_local, "cache_hits", 0)


def llm_json_call(model_name: str, prompt: str) -> dict | None:
    cfg = load_config()
    try:
        raw, token_cost = chat_completion(
            model_name,
            [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            base_url=cfg["llm"]["base_url"],
            temperature=0.0,
            llm_cfg=cfg["llm"],
        )
        _accumulate(token_cost)
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None

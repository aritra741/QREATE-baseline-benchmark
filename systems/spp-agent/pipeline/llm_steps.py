"""Shared LLM call helpers for population steps."""

from __future__ import annotations

import json

from llm.client import chat_completion
from utils.config import load_config


def llm_json_call(model_name: str, prompt: str) -> dict | None:
    cfg = load_config()
    try:
        raw, _ = chat_completion(
            model_name,
            [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            base_url=cfg["llm"]["base_url"],
            temperature=0.0,
            llm_cfg=cfg["llm"],
        )
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None
